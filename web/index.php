<?php require __DIR__ . '/bootstrap.php'; ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="csrf-token" content="<?= htmlspecialchars($_SESSION['csrf'], ENT_QUOTES, 'UTF-8') ?>">
<meta name="description" content="Archive public websites for offline browsing with Web Copy Lite.">
<title>Web Copy Lite · Take the web with you</title>
<link rel="stylesheet" href="assets/style.css"><script src="assets/app.js" defer></script>
</head>
<body>
<div class="app-shell">
<aside class="sidebar">
<a class="brand" href="./"><span class="brand-mark">W<span>↘</span></span><span>web copy<span class="lite">LITE</span></span></a>
<div class="workspace-label">YOUR WORKSPACE</div>
<a class="nav-item active" href="./"><span>▧</span> Website archive <span class="nav-dot"></span></a>
<a class="nav-item" href="https://github.com/DOVEPCDIABLE/wc-light" target="_blank" rel="noopener"><span>⌘</span> Source & documentation <span>↗</span></a>
<div class="sidebar-bottom"><span class="status-dot"></span> Python engine / PHP interface<div class="version">OPEN SOURCE · V1.0</div></div>
</aside>
<main>
<header class="topbar"><span>Workspace <span class="slash">/</span> <strong>Website archive</strong></span><a href="https://github.com/DOVEPCDIABLE/wc-light" target="_blank" rel="noopener">View on GitHub ↗</a></header>
<div class="content">
<div class="eyebrow"><span class="status-dot"></span> THE WEB, ON YOUR TERMS</div>
<div class="heading-row"><div><h1>Take the web<br><span>with you.</span></h1><p class="intro">Turn a public website into a portable archive.<br>Pages, styles, and assets. Ready when you’re offline.</p></div><div class="archive-art" aria-hidden="true"><div class="art-line"></div><div class="art-card back">&lt;/&gt;</div><div class="art-card front"><span>↘</span><small>OFFLINE<br>READY</small></div><span class="art-spark">✳</span></div></div>
<div class="main-grid">
<section class="panel form-panel"><div class="panel-heading"><div><span class="step">01</span><h2>Create an archive</h2></div><span class="tag">NEW COPY</span></div>
<form id="archive-form">
<label for="url">Website URL</label><div class="url-input"><span>↗</span><input id="url" name="url" type="url" placeholder="https://example.com" required maxlength="2048" autocomplete="url"></div><p class="field-note">Start with any public page. We’ll follow links on the same hostname.</p>
<div class="settings-row"><div><label for="depth">Crawl depth</label><select id="depth"><option value="0">0 — This page only</option><option value="1">1 — Linked pages</option><option value="2" selected>2 — Two levels deep</option><option value="3">3 — Three levels deep</option><option value="4">4 — Four levels deep</option><option value="5">5 — Five levels deep</option></select></div><div><label for="max-resources">Resource limit</label><select id="max-resources"><option value="100">100 resources</option><option value="300" selected>300 resources</option><option value="500">500 resources</option><option value="1000">1,000 resources</option></select></div></div>
<details><summary>Advanced settings <span>＋</span></summary><div class="advanced"><label for="delay">Request interval (seconds)</label><input id="delay" type="number" value="0.5" min="0.1" max="5" step="0.1"><label for="user-agent">User-Agent</label><input id="user-agent" value="WebCopyLite/1.0 (authorized offline archiver)" maxlength="200"></div></details>
<div class="included"><span>✓ Styles & scripts</span><span>✓ Images & fonts</span><span>✓ Local links</span><span>✓ ZIP export</span></div>
<label class="permission"><input id="authorized" type="checkbox" required><span>I own this website or have permission to archive it.</span></label>
<button class="primary" id="submit" type="submit"><span>Create offline archive</span><span>↘</span></button>
<p class="error" id="error" role="alert" hidden></p>
<div class="form-footer"><span class="tiny-shield">◇</span> Public URLs only. robots.txt respected. Private networks blocked.</div>
</form></section>
<section class="panel progress-panel"><div class="panel-heading"><div><span class="step">02</span><h2>Your archive</h2></div><span class="state-tag" id="state-tag">STANDBY</span></div>
<div id="idle" class="idle"><div class="idle-icon">▤<span>↓</span></div><h3>A little piece of the web.<br>All yours to keep.</h3><p>Your archive will appear here.<br>Add a URL and we’ll take care of the rest.</p><div class="idle-path"><span>Website</span><i>→</i><span>Local files</span><i>→</i><span>.zip</span></div></div>
<div id="job" hidden><div class="job-title" id="job-title">Preparing your archive…</div><p class="job-url" id="job-url"></p><div class="activity-track"><span id="activity"></span></div><div class="stats"><div><strong id="copied">0</strong><span>Copied</span></div><div><strong id="failed">0</strong><span>Failed</span></div><div><strong id="size">0 KB</strong><span>Downloaded</span></div></div><div class="log-heading">ACTIVITY LOG <span id="elapsed">0s</span></div><div class="logs" id="logs" aria-label="Resource activity"></div><p id="result-note" class="field-note" aria-live="polite"></p><a id="download" class="primary download" hidden>Download ZIP <span>↓</span></a></div>
</section></div>
<div class="principles"><div><span class="feature-icon">⌁</span><div><h3>Built for offline</h3><p>Relative links keep copied pages connected.</p></div></div><div><span class="feature-icon">◇</span><div><h3>Respectful by default</h3><p>Rate limits and robots.txt guide every crawl.</p></div></div><div><span class="feature-icon">&lt;/&gt;</span><div><h3>Yours to explore</h3><p>An independent engine. An open source toolkit.</p></div></div></div>
<footer><span>WEB COPY LITE <span class="footer-divider">/</span> A small tool for a portable web.</span><span>Made for authorized archiving ↗</span></footer>
</div></main></div>
</body></html>
