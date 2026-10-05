"""Bounded concurrent crawl and a second pass that rewrites saved resources."""
import hashlib
import json
import mimetypes
import os
import re
import threading
import time
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import tinycss2
from .network import FetchError, SafeClient, normalize


@dataclass
class Options:
    url: str
    depth: int = 2
    workers: int = 4
    delay: float = 0.5
    max_resources: int = 500
    max_bytes: int = 15 * 1024 * 1024
    max_total_bytes: int = 250 * 1024 * 1024
    user_agent: str = "WebCopyLite/1.0 (authorized offline archiver)"
    respect_robots: bool = True
    render: bool = False

    def validate(self):
        self.url = normalize(self.url)
        for value, low, high, label in ((self.depth, 0, 10, "depth"), (self.workers, 1, 8, "workers"),
                                        (self.max_resources, 1, 5000, "max_resources"),
                                        (self.max_bytes, 1024, 50 * 1024 * 1024, "max_bytes"),
                                        (self.max_total_bytes, 1024, 1024 * 1024 * 1024, "max_total_bytes")):
            if not isinstance(value, int) or not low <= value <= high:
                raise ValueError("{} must be between {} and {}".format(label, low, high))
        if not 0.1 <= self.delay <= 30:
            raise ValueError("delay must be between 0.1 and 30 seconds")
        if not self.user_agent or len(self.user_agent) > 200 or any(ord(c) < 32 or ord(c) > 126 for c in self.user_agent):
            raise ValueError("User-Agent must be 1–200 printable ASCII characters")
        return self


def css_transform(source, callback):
    """Use CSS tokens so escaped URLs, comments and nested rules are preserved."""
    tokens = tinycss2.parse_component_value_list(source)
    def visit(items):
        previous_import = False
        for token in items:
            if token.type == "url":
                value = callback(token.value)
                token.value = value
                token.representation = 'url(' + json.dumps(value) + ')'
            elif token.type == "function" and token.lower_name == "url":
                arguments = [item for item in token.arguments if item.type not in ("whitespace", "comment")]
                value = arguments[0].value if len(arguments) == 1 and arguments[0].type == "string" else tinycss2.serialize(token.arguments).strip().strip('"\'')
                value = callback(value)
                token.arguments = tinycss2.parse_component_value_list(json.dumps(value))
            elif token.type == "string" and previous_import:
                value = callback(token.value)
                token.value = value
                token.representation = json.dumps(value)
            if token.type not in ("whitespace", "comment"):
                previous_import = token.type == "at-keyword" and token.value.lower() == "import"
            if hasattr(token, "content"):
                visit(token.content)
            if token.type == "function" and token.lower_name != "url":
                visit(token.arguments)
    visit(tokens)
    return tinycss2.serialize(tokens)


def srcset_transform(source, callback):
    # Data URIs include commas and should stay inline. Do not split them.
    if "data:" in source.lower():
        return source
    entries = []
    for part in source.split(","):
        parts = part.strip().split(None, 1)
        if parts:
            entries.append(callback(parts[0]) + (" " + parts[1] if len(parts) > 1 else ""))
    return ", ".join(entries)


class Archive:
    def __init__(self, options, output, progress=None, client=None):
        self.options = options.validate()
        self.output = Path(output)
        self.site = self.output / "site"
        self.client = client or SafeClient(options.user_agent, max_bytes=options.max_bytes)
        self.progress = progress or (lambda state: None)
        self.host = urlsplit(options.url).hostname
        self.queue = deque()
        self.seen = set()
        self.resources = {}
        self.aliases = {}
        self.asset_hashes = {}
        self.events = []
        self.robots = {}
        self.robots_lock = threading.RLock()
        self.rate_lock = threading.Lock()
        self.next_request = {}
        self.total_bytes = 0
        self.started = time.time()
        self.phase = "running"
        self.limit_reported = False

    def state(self):
        return {"status": self.phase, "url": self.options.url, "copied": len(self.resources),
                "failed": sum(e["status"] == "failed" for e in self.events),
                "skipped": sum(e["status"] == "skipped" for e in self.events),
                "bytes": self.total_bytes, "queued": len(self.queue),
                "elapsed": round(time.time() - self.started, 1), "logs": self.events[-80:]}

    def log(self, status, url, message):
        self.events.append({"status": status, "url": url, "message": message})
        self.progress(self.state())

    def rate_limit(self, url, delay=None):
        origin = urlsplit(url).netloc
        with self.rate_lock:
            now = time.monotonic()
            scheduled = max(now, self.next_request.get(origin, now))
            self.next_request[origin] = scheduled + (delay if delay is not None else self.options.delay)
        time.sleep(max(0, scheduled - now))

    def policy(self, url, page=False):
        if page and urlsplit(url).hostname != self.host:
            raise FetchError("Page redirect left starting hostname")
        if not self.options.respect_robots:
            self.rate_limit(url)
            return
        p = urlsplit(url)
        origin = urlunsplit((p.scheme, p.netloc, "", "", ""))
        with self.robots_lock:
            if origin not in self.robots:
                parser = RobotFileParser(origin + "/robots.txt")
                try:
                    response = self.client.get(origin + "/robots.txt", before_request=self.rate_limit)
                    parser.parse(response.text().splitlines())
                except FetchError as exc:
                    # Missing robots permits access. Network failure, 403 and
                    # server errors fail closed rather than guessing permission.
                    parser.parse([] if str(exc) in ("HTTP 404", "HTTP 410") else ["User-agent: *", "Disallow: /"])
                self.robots[origin] = parser
            parser = self.robots[origin]
        if not parser.can_fetch(self.options.user_agent, url):
            raise FetchError("Skipped by robots.txt")
        delay = max(self.options.delay, parser.crawl_delay(self.options.user_agent) or 0)
        rate = parser.request_rate(self.options.user_agent)
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        if delay > 30:
            raise FetchError("Skipped by robots.txt: required delay exceeds supported 30 seconds")
        self.rate_limit(url, delay)

    def enqueue(self, value, base, depth, page=False):
        if not value or value.startswith("#"):
            return
        try:
            url = normalize(value, base)
        except FetchError:
            return
        if page and (depth > self.options.depth or urlsplit(url).hostname != self.host):
            return
        if url in self.seen:
            return
        if len(self.seen) >= self.options.max_resources:
            if not self.limit_reported:
                self.limit_reported = True
                self.log("skipped", url, "Resource limit reached; remaining discoveries omitted")
            return
        self.seen.add(url)
        self.queue.append((url, depth, page))

    def html_transform(self, source, base, callback, discover=False, depth=0):
        soup = BeautifulSoup(source, "html.parser")
        base_tag = soup.find("base", href=True)
        document_base = base
        if base_tag:
            try:
                document_base = normalize(base_tag["href"], base)
            except FetchError:
                pass
        def use(value, page=False):
            if discover:
                self.enqueue(value, document_base, depth + 1 if page else depth, page)
                return value
            return callback(value, document_base)
        for tag in soup.find_all(True):
            if tag.name == "a" and tag.get("href"):
                tag["href"] = use(tag["href"], True)
            elif tag.name == "link" and tag.get("href"):
                rel = set(tag.get("rel", []))
                if rel.intersection({"stylesheet", "icon", "preload", "modulepreload", "apple-touch-icon"}):
                    tag["href"] = use(tag["href"])
            for attr in ("src", "poster", "data-src"):
                if tag.get(attr):
                    tag[attr] = use(tag[attr], tag.name in ("iframe", "frame"))
            for attr in ("srcset", "data-srcset"):
                if tag.get(attr):
                    tag[attr] = srcset_transform(tag[attr], use)
            if tag.get("style"):
                tag["style"] = css_transform(tag["style"], use)
            if tag.name == "style" and tag.string:
                tag.string.replace_with(css_transform(str(tag.string), use))
            if not discover:
                # Rewriting bytes invalidates SRI. Remote base and CSP directives
                # can prevent local files from loading.
                for attr in ("integrity", "crossorigin"):
                    tag.attrs.pop(attr, None)
        if not discover:
            for tag in soup.find_all("base"):
                tag.decompose()
            for tag in soup.find_all("meta"):
                if str(tag.get("http-equiv", "")).lower() in ("content-security-policy", "refresh"):
                    tag.decompose()
            if soup.head:
                if soup.head.find("meta", charset=True):
                    soup.head.find("meta", charset=True)["charset"] = "utf-8"
                else:
                    soup.head.insert(0, soup.new_tag("meta", charset="utf-8"))
        return str(soup)

    def filename(self, url, response):
        digest = hashlib.sha256(url.encode()).hexdigest()[:24]
        suffix = Path(urlsplit(url).path).suffix.lower()
        ct = response.content_type
        if ct in ("text/html", "application/xhtml+xml"):
            suffix = ".html"
        elif ct == "text/css":
            suffix = ".css"
        elif ct in ("application/javascript", "text/javascript"):
            suffix = ".js"
        elif suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".webm", ".mp3", ".wav", ".pdf", ".json", ".txt", ".css", ".js"}:
            suffix = mimetypes.guess_extension(ct) or ".bin"
        return "resources/{}{}".format(digest, suffix)

    def fetch(self, item):
        url, depth, page = item
        response = self.client.get(url, before_request=lambda target: self.policy(target, page))
        if self.options.render and page and response.content_type in ("text/html", "application/xhtml+xml"):
            from .render import render_html
            response.body = render_html(response.url, self.client, lambda target: self.policy(target), self.options).encode()
            response.headers["content-type"] = "text/html; charset=utf-8"
        return response

    def run(self):
        self.site.mkdir(parents=True, exist_ok=False)
        self.enqueue(self.options.url, self.options.url, 0, True)
        self.progress(self.state())
        with ThreadPoolExecutor(max_workers=self.options.workers) as pool:
            while self.queue:
                batch = [self.queue.popleft() for _ in range(min(len(self.queue), self.options.workers))]
                futures = {pool.submit(self.fetch, item): item for item in batch}
                for future in as_completed(futures):
                    url, depth, page = futures[future]
                    try:
                        response = future.result()
                        if len(response.body) + self.total_bytes > self.options.max_total_bytes:
                            self.log("skipped", url, "Total archive byte limit reached")
                            continue
                        self.aliases[url] = response.url
                        if response.url in self.resources:
                            self.log("skipped", url, "Redirect destination already copied")
                            continue
                        filename = self.filename(response.url, response)
                        if response.content_type not in ("text/html", "application/xhtml+xml", "text/css", "application/javascript", "text/javascript"):
                            fingerprint = (response.content_type, hashlib.sha256(response.body).hexdigest())
                            filename = self.asset_hashes.setdefault(fingerprint, filename)
                        self.resources[response.url] = {"path": filename, "response": response, "depth": depth}
                        self.total_bytes += len(response.body)
                        (self.site / filename).parent.mkdir(parents=True, exist_ok=True)
                        (self.site / filename).write_bytes(response.body)
                        if response.content_type in ("text/html", "application/xhtml+xml"):
                            self.html_transform(response.text(), response.url, None, True, depth)
                        elif response.content_type == "text/css":
                            css_transform(response.text(), lambda value: self.discover_asset(value, response.url, depth))
                        self.log("copied", url, filename)
                    except Exception as exc:
                        self.log("skipped" if "robots.txt" in str(exc) else "failed", url, str(exc))
        self.phase = "rewriting"
        self.progress(self.state())
        for url, resource in self.resources.items():
            response = resource["response"]
            def rewrite(value, base=url):
                if value.startswith("#"):
                    return value
                try:
                    target = normalize(value, base)
                    canonical = self.aliases.get(target, target)
                    entry = self.resources.get(canonical)
                    if not entry:
                        # Retain a valid online fallback for resources not copied.
                        return normalize(value, base) + ("#" + urlsplit(value).fragment if urlsplit(value).fragment else "")
                    relative = os.path.relpath(entry["path"], os.path.dirname(resource["path"])).replace(os.sep, "/")
                    return relative + ("#" + urlsplit(value).fragment if urlsplit(value).fragment else "")
                except FetchError:
                    return value
            if response.content_type in ("text/html", "application/xhtml+xml"):
                (self.site / resource["path"]).write_text(self.html_transform(response.text(), url, rewrite), encoding="utf-8")
            elif response.content_type == "text/css":
                (self.site / resource["path"]).write_text(css_transform(response.text(), rewrite), encoding="utf-8")
        root = self.resources.get(self.aliases.get(self.options.url, self.options.url))
        if not root:
            self.phase = "failed"
            self.write_report()
            self.progress(self.state())
            raise FetchError("Starting page could not be copied; see crawl report")
        # A small local entrypoint keeps all page paths in one stable namespace.
        from html import escape
        entry = escape(root["path"], quote=True)
        (self.site / "index.html").write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=' + entry + '"><title>Web Copy Lite archive</title><a href="' + entry + '">Open archived website</a>', encoding="utf-8")
        self.phase = "complete"
        self.write_report()
        archive = self.output / "archive.zip"
        with zipfile.ZipFile(archive.with_suffix(".tmp"), "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(self.site.rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(self.site))
        archive.with_suffix(".tmp").replace(archive)
        self.progress(self.state())
        return archive

    def discover_asset(self, value, base, depth):
        self.enqueue(value, base, depth)
        return value

    def write_report(self):
        report = {"options": asdict(self.options), "summary": self.state(), "logs": self.events,
                  "resources": {url: r["path"] for url, r in self.resources.items()}}
        (self.site / "crawl-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
