<?php
declare(strict_types=1);
// The browser UI is local-only by default. Public deployment requires separate
// authentication and an explicit WCL_ALLOW_REMOTE=1 opt-in.
if (getenv('WCL_ALLOW_REMOTE') !== '1' && !in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1'], true)) {
    http_response_code(403);
    exit('Web Copy Lite is local-only. See the deployment instructions.');
}
ini_set('session.use_strict_mode', '1');
session_set_cookie_params(['httponly' => true, 'samesite' => 'Strict', 'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off']);
session_start();
$_SESSION['csrf'] ??= bin2hex(random_bytes(32));
$_SESSION['jobs'] ??= [];
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');
header('Cache-Control: no-store');
header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");

function storage(): string {
    $root = getenv('WCL_STORAGE') ?: sys_get_temp_dir() . '/webcopy-lite-' . substr(hash('sha256', dirname(__DIR__)), 0, 16);
    if (!is_dir($root) && !mkdir($root, 0700, true)) throw new RuntimeException('Cannot create job storage');
    $root = realpath($root);
    $docroot = realpath($_SERVER['DOCUMENT_ROOT'] ?? __DIR__);
    if ($docroot && ($root === $docroot || str_starts_with($root, $docroot . DIRECTORY_SEPARATOR))) {
        throw new RuntimeException('WCL_STORAGE must be outside the web document root');
    }
    if (!is_writable($root)) throw new RuntimeException('Job storage is not writable');
    return $root;
}

function json_response(array $data, int $code = 200): never {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

function job_directory(string $id): string {
    if (!preg_match('/^[a-f0-9]{32}$/D', $id) || !in_array($id, $_SESSION['jobs'], true)) {
        throw new RuntimeException('Job not found');
    }
    return storage() . '/' . $id;
}
