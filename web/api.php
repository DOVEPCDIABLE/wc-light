<?php
declare(strict_types=1);
require __DIR__ . '/bootstrap.php';
try {
    $action = $_GET['action'] ?? '';
    if ($action === 'status' && $_SERVER['REQUEST_METHOD'] === 'GET') {
        $directory = job_directory((string)($_GET['id'] ?? ''));
        session_write_close();
        $state = json_decode((string)@file_get_contents($directory . '/status.json'), true);
        if (!$state) throw new RuntimeException('Status unavailable');
        // Detect a worker that died before it could report failure.
        if (in_array($state['status'], ['queued', 'running', 'rewriting'], true) && time() - filemtime($directory . '/status.json') > 180) {
            $state['status'] = 'failed';
            $state['error'] = 'Worker stopped responding. Check worker.log and Python configuration.';
        }
        json_response($state);
    }
    if ($action !== 'start' || $_SERVER['REQUEST_METHOD'] !== 'POST') json_response(['error' => 'Unknown endpoint'], 404);
    $input = json_decode(file_get_contents('php://input', false, null, 0, 8192), true, 16, JSON_THROW_ON_ERROR);
    if (!hash_equals($_SESSION['csrf'], (string)($input['csrf'] ?? ''))) json_response(['error' => 'Session expired. Reload the page.'], 403);
    if (($input['authorized'] ?? false) !== true) json_response(['error' => 'Confirm that you have permission to archive this website.'], 422);
    $url = trim((string)($input['url'] ?? ''));
    $parts = parse_url($url);
    if (strlen($url) > 2048 || !$parts || !in_array(strtolower($parts['scheme'] ?? ''), ['http', 'https'], true) || empty($parts['host']) || isset($parts['user']) || isset($parts['pass'])) {
        json_response(['error' => 'Enter a full public HTTP or HTTPS URL.'], 422);
    }
    $depth = filter_var($input['depth'] ?? 2, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0, 'max_range' => 5]]);
    $limit = filter_var($input['max_resources'] ?? 300, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 1000]]);
    $delay = filter_var($input['delay'] ?? 0.5, FILTER_VALIDATE_FLOAT);
    $agent = (string)($input['user_agent'] ?? 'WebCopyLite/1.0 (authorized offline archiver)');
    if ($depth === false || $limit === false || $delay === false || $delay < 0.1 || $delay > 5 || !preg_match('/^[\x20-\x7e]{1,200}$/D', $agent)) {
        json_response(['error' => 'Invalid crawl settings.'], 422);
    }
    if (PHP_OS_FAMILY === 'Windows' || !is_callable('exec')) throw new RuntimeException('The PHP worker launcher requires macOS/Linux and PHP exec. Use the Python CLI on Windows.');
    $root = storage();
    $lock = fopen($root . '/jobs.lock', 'c');
    if (!$lock || !flock($lock, LOCK_EX)) throw new RuntimeException('Could not lock job queue');
    $active = 0;
    foreach (glob($root . '/*/status.json') ?: [] as $file) {
        $state = json_decode((string)file_get_contents($file), true);
        if ($state && in_array($state['status'], ['queued', 'running', 'rewriting'], true) && time() - filemtime($file) < 180) {
            $active++;
            if (in_array(basename(dirname($file)), $_SESSION['jobs'], true)) json_response(['error' => 'Your archive is already running.'], 409);
        }
    }
    if ($active >= 3) json_response(['error' => 'Three archives are already running. Try again shortly.'], 429);
    $python = getenv('WCL_PYTHON') ?: dirname(__DIR__) . '/.venv/bin/python';
    if (!is_executable($python)) throw new RuntimeException('Python environment missing. Run python3 -m venv .venv and .venv/bin/pip install -e .');
    $id = bin2hex(random_bytes(16));
    $directory = $root . '/' . $id;
    mkdir($directory, 0700);
    $options = ['url' => $url, 'depth' => $depth, 'workers' => 4, 'delay' => $delay,
                'max_resources' => $limit, 'user_agent' => $agent, 'respect_robots' => true, 'render' => false];
    file_put_contents($directory . '/job.json', json_encode(['options' => $options], JSON_THROW_ON_ERROR));
    file_put_contents($directory . '/status.json', json_encode(['status' => 'queued', 'copied' => 0, 'failed' => 0, 'skipped' => 0, 'bytes' => 0, 'queued' => 1, 'logs' => []]));
    $command = 'cd ' . escapeshellarg(dirname(__DIR__)) . ' && ' . escapeshellarg($python) . ' -m webcopy --job ' . escapeshellarg($directory . '/job.json') . ' > ' . escapeshellarg($directory . '/worker.log') . ' 2>&1 & echo $!';
    exec($command, $result, $code);
    if ($code !== 0 || empty($result)) throw new RuntimeException('Could not launch Python worker');
    $_SESSION['jobs'][] = $id;
    $_SESSION['jobs'] = array_slice($_SESSION['jobs'], -30);
    flock($lock, LOCK_UN);
    fclose($lock);
    json_response(['id' => $id], 202);
} catch (Throwable $error) {
    json_response(['error' => $error->getMessage()], 400);
}
