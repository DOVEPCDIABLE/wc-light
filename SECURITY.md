# Security

Report vulnerabilities through the repository's GitHub security advisories where available. Avoid publishing working exploit details before a fix is available.

The PHP interface defaults to loopback clients. Session-scoped jobs and CSRF checks do not replace authentication for remote deployments. Set `WCL_ALLOW_REMOTE=1` only behind authenticated access. Keep job storage outside the web document root. Use operating system quotas and cleanup policies for retained archives.

The Python transport validates all resolved addresses, connects to a validated IP, verifies HTTPS certificates against the original hostname, rejects internal networks and rechecks redirects. It ignores proxy environment variables. Network infrastructure should independently deny internal and metadata destinations when this application is hosted.

Optional browser rendering executes page code. Run it in an isolated environment with restrictive network egress. Rendering is intentionally unavailable through the PHP interface.

Exports contain original third-party scripts and media. Treat archives as untrusted content, use an isolated browser profile, and do not serve downloaded files on a privileged origin or with a PHP interpreter. V1 makes a static archive; it does not sanitize scripts or guarantee offline network isolation.
