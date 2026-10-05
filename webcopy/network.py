"""HTTP transport with public-only DNS validation and pinned connections.

No proxy environment variables are used. Every redirect is revalidated.
"""
import http.client
import ipaddress
import socket
import ssl
import time
import zlib
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlsplit, urlunsplit


# Keep conservative exclusions explicit across supported Python versions;
# ipaddress's special-purpose registry changes between Python releases.
BLOCKED_V4 = tuple(ipaddress.ip_network(cidr) for cidr in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4"))
BLOCKED_V6 = tuple(ipaddress.ip_network(cidr) for cidr in (
    "2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20"))


class FetchError(ValueError):
    pass


def normalize(url, base=None):
    url = urljoin(base, url.strip()) if base else url.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in url) or "\\" in url:
        raise FetchError("Invalid URL characters")
    try:
        p = urlsplit(url)
        if p.scheme.lower() not in ("http", "https") or not p.hostname:
            raise FetchError("Only HTTP and HTTPS URLs are supported")
        if p.username is not None or p.password is not None:
            raise FetchError("URL credentials are not allowed")
        host = p.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = p.port
    except (ValueError, UnicodeError) as exc:
        raise FetchError(str(exc)) from exc
    if port not in (None, 80, 443):
        raise FetchError("Only ports 80 and 443 are allowed")
    authority = "[{}]".format(host) if ":" in host else host
    if port and port != (443 if p.scheme.lower() == "https" else 80):
        authority += ":{}".format(port)
    # Keep query ordering and encoding: changing them can alter server behavior.
    return urlunsplit((p.scheme.lower(), authority, quote(p.path or "/", safe="/%:@!$&'()*+,;=-._~"), quote(p.query, safe="%:@!$&'()*+,;=/?-._~"), ""))


def public_addresses(host, port):
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise FetchError("Local network hosts are blocked")
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError("DNS lookup failed: {}".format(exc)) from exc
    addresses = list(dict.fromkeys(item[4][0] for item in answers))
    if not addresses:
        raise FetchError("Host has no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        # Explicit IPv6 transition checks prevent tunneling into private IPv4.
        if not ip.is_global or ip.is_multicast or ip.is_unspecified:
            raise FetchError("Non-public network address blocked")
        if isinstance(ip, ipaddress.IPv4Address) and any(ip in network for network in BLOCKED_V4):
            raise FetchError("Special-purpose network address blocked")
        if isinstance(ip, ipaddress.IPv6Address):
            if ip not in ipaddress.ip_network("2000::/3") or any(ip in network for network in BLOCKED_V6):
                raise FetchError("Non-public or special-purpose IPv6 address blocked")
            if ip.ipv4_mapped or ip.sixtofour or ip.teredo or ip in ipaddress.ip_network("64:ff9b::/96"):
                raise FetchError("IPv6 transition addresses are blocked")
    return addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


@dataclass
class Response:
    url: str
    status: int
    headers: dict
    body: bytes

    @property
    def content_type(self):
        return self.headers.get("content-type", "").split(";", 1)[0].lower()

    def text(self):
        import re
        match = re.search(r"charset=[\"']?([^;\s\"']+)", self.headers.get("content-type", ""), re.I)
        try:
            return self.body.decode(match.group(1) if match else "utf-8", errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


class SafeClient:
    def __init__(self, user_agent, timeout=20, max_bytes=15 * 1024 * 1024, retries=2):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.retries = retries

    def get(self, url, before_request=None):
        url = normalize(url)
        for hop in range(11):
            if hop == 10:
                raise FetchError("Too many redirects")
            p = urlsplit(url)
            port = p.port or (443 if p.scheme == "https" else 80)
            response = None
            for attempt in range(self.retries + 1):
                # Re-resolve and validate ALL records on every connection; the
                # socket uses the checked IP, so DNS cannot change it afterward.
                addresses = public_addresses(p.hostname, port)
                if before_request:
                    before_request(url)
                conn = (PinnedHTTPS(p.hostname, port, addresses[attempt % len(addresses)], self.timeout)
                        if p.scheme == "https" else
                        http.client.HTTPConnection(addresses[attempt % len(addresses)], port, timeout=self.timeout))
                try:
                    target = urlunsplit(("", "", p.path or "/", p.query, ""))
                    conn.request("GET", target, headers={"Host": p.netloc, "User-Agent": self.user_agent,
                                                        "Accept-Encoding": "identity", "Connection": "close"})
                    raw = conn.getresponse()
                    headers = {k.lower(): v for k, v in raw.getheaders()}
                    body = raw.read(self.max_bytes + 1)
                    if len(body) > self.max_bytes:
                        raise FetchError("Resource exceeds download size limit")
                    encoding = headers.get("content-encoding", "").lower()
                    if encoding in ("gzip", "deflate"):
                        dec = zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
                        body = dec.decompress(body, self.max_bytes + 1)
                        if len(body) > self.max_bytes or dec.unconsumed_tail or not dec.eof:
                            raise FetchError("Compressed resource exceeds limit or is incomplete")
                    elif encoding not in ("", "identity"):
                        raise FetchError("Unsupported content encoding")
                    response = Response(url, raw.status, headers, body)
                    if raw.status in (429, 500, 502, 503, 504) and attempt < self.retries:
                        time.sleep(min(2 ** attempt, 4))
                        continue
                    break
                except (OSError, http.client.HTTPException) as exc:
                    if attempt == self.retries:
                        raise FetchError("Network request failed: {}".format(exc)) from exc
                    time.sleep(min(2 ** attempt, 4))
                finally:
                    conn.close()
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError("Redirect has no Location")
                url = normalize(location, url)
                continue
            if not 200 <= response.status < 300:
                raise FetchError("HTTP {}".format(response.status))
            return response
        raise FetchError("Redirect limit exceeded")
