<?php
declare(strict_types=1);
require __DIR__ . '/bootstrap.php';
try {
    $directory = job_directory((string)($_GET['id'] ?? ''));
    session_write_close();
    $file = $directory . '/archive.zip';
    $state = json_decode((string)@file_get_contents($directory . '/status.json'), true);
    if (($state['status'] ?? '') !== 'complete' || !is_file($file)) {
        http_response_code(409);
        exit('Archive is not ready.');
    }
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="web-copy-lite.zip"');
    header('Content-Length: ' . filesize($file));
    readfile($file);
} catch (Throwable $error) {
    http_response_code(404);
    echo 'Archive not found.';
}
