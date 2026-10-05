# Web Copy Lite

**Take the web with you.** A Python website archiver with an optional PHP + HTML/CSS/JavaScript interface. Copy an authorized public website into a ZIP of locally linked pages and assets for offline browsing.

Web Copy Lite creates a static snapshot of public content. It does not reproduce a website's backend, accounts, payments, or database. Archive sites you own or have permission to copy and comply with their terms and content licenses.

## Quick start

Requires Python 3.9+; the optional browser UI requires PHP 8.1+ and macOS/Linux with PHP `exec` enabled. The Python CLI also works on Windows.

```sh
git clone https://github.com/DOVEPCDIABLE/wc-light.git
cd wc-light
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e .
.venv/bin/python -m webcopy https://example.com --output output/example
```

On Windows, use `py -m venv .venv`, `.venv\Scripts\pip install -e .` and `.venv\Scripts\python -m webcopy ...`.

Extract `archive.zip`, then open `index.html`. Some browser features need HTTP rather than `file://`; serve a **trusted** extracted archive locally with `python3 -m http.server 8001 --bind 127.0.0.1 --directory output/example/site`. Archived JavaScript is third-party code and can still contact online services. Copying is not a sandbox or an offline execution guarantee.

## Browser interface

From the repository root, after installing the Python dependencies:

```sh
php -S 127.0.0.1:8080 -t web
```

Open **http://127.0.0.1:8080**. Enter a public URL, choose depth and resource limits, confirm authorization, and start an archive. The interface reports copied/failed resources and provides a ZIP download. Reloading the same browser tab reconnects to an active job.

### XAMPP

Use PHP 8.1 or newer. This checkout is compatible with an XAMPP `htdocs/wc-light` directory: open `http://localhost/wc-light/` (which redirects to `web/`) after installing `.venv`. Only `web/` should be exposed for a dedicated deployment. PHP must have execute permission on the Python interpreter and write permission on the job directory. If XAMPP runs as another user, configure a dedicated virtual environment and storage directory accessible to that user.

Configuration through environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `WCL_PYTHON` | `<repository>/.venv/bin/python` | Absolute path to the installed interpreter |
| `WCL_STORAGE` | App-specific directory in the OS temporary directory | Job files, logs and archives; must be outside the HTTP document root |
| `WCL_ALLOW_REMOTE` | Disabled | Set to `1` only behind your own authenticated access layer |

The UI is local-only by default and has session-owned job access, CSRF checks, safe subprocess arguments and a three-active-job cap. **It does not include user accounts.** Do not expose it as an anonymous public service. For remote use, add HTTPS, authentication, storage quotas, process supervision, and an outbound firewall blocking internal networks. Delete completed job directories from `WCL_STORAGE` periodically; V1 does not automatically expire them. Session ownership expires with the PHP session.

## V1 features

- Recursive page crawling with depth and starting-hostname restriction; public CDN assets allowed.
- HTML, CSS, scripts, images, fonts, media sources, common lazy-image attributes and `srcset`.
- CSS `url(...)` and `@import` discovery, including nested stylesheet dependencies.
- Two-pass local URL rewriting, base URL handling, fragment preservation and relative links.
- Duplicate URL suppression, binary asset content deduplication, redirect aliases, safe hashed filenames and separate query-string variants.
- Concurrent downloads, configurable per-origin pacing, retries, timeouts and resource/byte limits.
- Redirect validation on every hop; HTTP/HTTPS on ports 80/443 only.
- `robots.txt` checks for pages and assets, crawl-delay and request-rate awareness.
- CLI progress, PHP live activity, ZIP export and a complete `crawl-report.json`.
- Optional Playwright rendered DOM capture through the CLI.
- SSRF defense: reject credentials, non-HTTP schemes, localhost, private/reserved/multicast IPs, cloud metadata addresses and IPv6 transition addresses. Validate all DNS records and pin connections to checked IPs; HTTPS keeps hostname verification. Proxy environment variables are not used.

A hostname restriction treats `www.example.com` and `example.com` as different hosts. Start with the site's canonical URL. Cross-host page redirects are blocked; asset redirects may go to another public host.

## CLI options

```sh
webcopy https://example.com \
  --output output/example \
  --depth 2 --workers 4 --delay 0.5 --max-resources 500 \
  --user-agent 'WebCopyLite/1.0 (authorized offline archiver)'
```

Use `.venv/bin/webcopy` if the virtual environment is not activated. Output destinations must be fresh: the engine refuses to overwrite an existing `site/` directory. Defaults: 15 MiB per resource, 250 MiB total downloaded archive resources, two retries after the initial attempt, and a 20-second socket timeout. Size totals describe fetched bytes before rewriting/ZIP compression.

`--ignore-robots` is available only in the CLI for explicit site-owner authorization. Missing robots files (404/410) permit crawling; inaccessible or failing robots files fail closed. The browser UI always respects robots rules.

### Optional rendered capture

```sh
.venv/bin/pip install -e '.[render]'
.venv/bin/playwright install chromium
.venv/bin/webcopy https://your-public-site.example --render --output output/rendered
```

Rendered capture waits for DOM readiness and then 1.5 seconds for updates. Service workers are disabled; browser HTTP requests are fulfilled through the same public-only transport instead of giving Chromium unrestricted URL fetching. WebSockets and common alternate transports are disabled. Rendering executes untrusted page code: use an isolated process/container and outbound firewall for untrusted sites. This mode is deliberately CLI-only. See [Playwright's network guidance](https://playwright.dev/python/docs/network) for service-worker routing behavior.

## Fidelity and limitations

Most static sites work well. Visual fidelity depends on what a site exposes publicly. Dynamic sites may need rendering and can still depend on APIs or state that cannot be exported. JavaScript is saved as-is: dynamically constructed URLs, module dependency graphs, runtime API calls, shadow DOM, user interactions, lazy content revealed by scrolling, and service-worker caches are not fully mirrored. Authentication, cookie sessions and POST requests are not supported. Mixed `data:` srcsets remain inline. Failed or excluded references retain online fallbacks; check the report for gaps. Offline archives are not guaranteed to make zero network requests.

Depth limits page traversal, while assets and CSS dependencies are followed independently within the resource limit. A resource discovered through both a page link and an asset reference is fetched once. Robots and rate limiting are per origin. IP checks protect server fetching; keep infrastructure egress controls as an additional boundary when hosting.

## Development

```sh
.venv/bin/python -m unittest discover -s tests -v
find web -name '*.php' -exec php -l {} \;
node --check web/assets/app.js
```

The fixture suite checks offline links, CSS imports, queries, redirects, depth, robots exclusions, limits, DNS rebinding defenses, and blocked network targets without connecting to private services. GitHub Actions runs it on Python 3.9, 3.12 and 3.13.

```text
webcopy/       Independent Python engine, transport, CLI and rendering adapter
web/           PHP endpoints and responsive browser interface
tests/         Deterministic crawler and security tests
```

MIT licensed. Contributions welcome: resume support, module-aware rewriting, snapshot comparisons and supervised worker queues are useful next steps.
