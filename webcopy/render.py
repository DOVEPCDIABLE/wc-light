"""Optional rendered DOM capture. Browser HTTP is fulfilled by SafeClient.

Never let Chromium perform arbitrary network requests directly.
"""
from urllib.parse import urlsplit
from .network import FetchError, normalize


def render_html(url, client, policy, options):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchError('Install rendering support: pip install ".[render]" and playwright install chromium') from exc
    count = 0
    total = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--disable-background-networking", "--disable-quic"])
        context = browser.new_context(service_workers="block", user_agent=options.user_agent, accept_downloads=False)
        def route_request(route):
            nonlocal count, total
            try:
                target = normalize(route.request.url)
                if route.request.method not in ("GET", "HEAD"):
                    raise FetchError("Capture only supports read-only GET requests")
                document = route.request.resource_type == "document"
                if document and urlsplit(target).hostname != urlsplit(options.url).hostname:
                    raise FetchError("Rendered page left starting hostname")
                count += 1
                if count > options.max_resources:
                    raise FetchError("Render request limit reached")
                response = client.get(target, before_request=policy)
                if document and urlsplit(response.url).hostname != urlsplit(options.url).hostname:
                    raise FetchError("Rendered page redirect left starting hostname")
                total += len(response.body)
                if total > options.max_total_bytes:
                    raise FetchError("Render byte limit reached")
                if response.url != target:
                    route.fulfill(status=302, headers={"location": response.url}, body="")
                    return
                headers = {k: v for k, v in response.headers.items() if k not in
                           ("content-length", "content-encoding", "transfer-encoding", "connection", "set-cookie")}
                route.fulfill(status=response.status, headers=headers, body=response.body)
            except Exception:
                route.abort()
        context.route("**/*", route_request)
        # Prevent alternate transports from bypassing the HTTP route guard.
        context.add_init_script("window.WebSocket = class { constructor(){throw new Error('Offline capture: WebSocket disabled')} }; window.RTCPeerConnection = undefined; window.WebTransport = undefined;")
        if hasattr(context, "route_web_socket"):
            context.route_web_socket("**/*", lambda ws: ws.close())
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            html = page.content()
            if len(html.encode()) > options.max_bytes:
                raise FetchError("Rendered DOM exceeds resource size limit")
            return html
        finally:
            browser.close()
