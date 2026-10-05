import json
import socket
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from webcopy.engine import Archive, Options, css_transform
from webcopy.network import FetchError, Response, SafeClient, normalize, public_addresses


class FixtureClient:
    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.calls = []

    def get(self, url, before_request=None):
        if before_request:
            before_request(url)
        self.calls.append(url)
        if url.endswith('/robots.txt'):
            return Response(url, 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /private\n')
        if url not in self.fixtures:
            raise FetchError('HTTP 404')
        target, kind, body = self.fixtures[url]
        if before_request and target != url:
            before_request(target)
        return Response(target, 200, {'content-type': kind}, body.encode() if isinstance(body, str) else body)


class ArchiveTests(unittest.TestCase):
    def test_offline_graph_and_queries(self):
        root = 'https://example.com/'
        fixtures = {
            root: (root, 'text/html', '''<html><head><base href="/nested/"><link rel="stylesheet" href="/main.css" integrity="x"><style>.x{background:url('/inline.png')}</style></head><body><a href="/about#section">About</a><a href="/private">private</a><a href="https://other.test/">External</a><img src="/photo?v=1" srcset="/photo?v=1 1x, /photo?v=2 2x"><script src="/app.js"></script></body></html>'''),
            'https://example.com/main.css': ('https://example.com/main.css', 'text/css', '@import "theme.css"; .x{background:url("https://cdn.test/bg.png")}'),
            'https://example.com/theme.css': ('https://example.com/theme.css', 'text/css', '@font-face{src:url("font.woff2")}'),
            'https://cdn.test/bg.png': ('https://cdn.test/bg.png', 'image/png', b'bg'),
            'https://example.com/font.woff2': ('https://example.com/font.woff2', 'font/woff2', b'font'),
            'https://example.com/inline.png': ('https://example.com/inline.png', 'image/png', b'inline'),
            'https://example.com/about': ('https://example.com/about/', 'text/html', '<a id="section" href="/deeper">Deeper</a>'),
            'https://example.com/photo?v=1': ('https://example.com/photo?v=1', 'image/png', b'one'),
            'https://example.com/photo?v=2': ('https://example.com/photo?v=2', 'image/png', b'two'),
            'https://example.com/app.js': ('https://example.com/app.js', 'text/javascript', 'console.log("archived")'),
        }
        client = FixtureClient(fixtures)
        with tempfile.TemporaryDirectory() as folder:
            archive = Archive(Options(root, depth=1, delay=.1), folder, client=client)
            archive.rate_limit = lambda *args: None
            result = archive.run()
            report = json.loads((Path(folder) / 'site/crawl-report.json').read_text())
            mapping = report['resources']
            self.assertNotEqual(mapping['https://example.com/photo?v=1'], mapping['https://example.com/photo?v=2'])
            html = (Path(folder) / 'site' / mapping[root]).read_text()
            self.assertNotIn('<base', html)
            self.assertNotIn('integrity=', html)
            self.assertIn(Path(mapping['https://example.com/about/']).name + '#section', html)
            self.assertIn('https://other.test/', html)
            self.assertNotIn('https://example.com/private', client.calls)
            self.assertNotIn('https://example.com/deeper', client.calls)
            css = (Path(folder) / 'site' / mapping['https://example.com/main.css']).read_text()
            self.assertIn(Path(mapping['https://cdn.test/bg.png']).name, css)
            self.assertIn(Path(mapping['https://example.com/theme.css']).name, css)
            with zipfile.ZipFile(result) as z:
                self.assertIn('index.html', z.namelist())
                self.assertIn('crawl-report.json', z.namelist())
                self.assertFalse(any(name.startswith('/') or '..' in name for name in z.namelist()))

    def test_binary_asset_content_deduplication(self):
        root = 'https://example.com/'
        fixtures = {
            root: (root, 'text/html', '<img src="a.png"><img src="b.png">'),
            root + 'a.png': (root + 'a.png', 'image/png', b'identical'),
            root + 'b.png': (root + 'b.png', 'image/png', b'identical'),
        }
        with tempfile.TemporaryDirectory() as folder:
            archive = Archive(Options(root), folder, client=FixtureClient(fixtures))
            archive.rate_limit = lambda *args: None
            archive.run()
            self.assertEqual(archive.resources[root+'a.png']['path'], archive.resources[root+'b.png']['path'])

    def test_limits_and_start_failure(self):
        client = FixtureClient({'https://example.com/': ('https://example.com/', 'text/html', '<img src="a"><img src="b">')})
        with tempfile.TemporaryDirectory() as folder:
            archive = Archive(Options('https://example.com/', max_resources=1), folder, client=client)
            archive.rate_limit = lambda *args: None
            archive.run()
            self.assertEqual(len(archive.resources), 1)
            self.assertTrue(any('limit' in event['message'] for event in archive.events))
        with tempfile.TemporaryDirectory() as folder:
            archive = Archive(Options('https://example.com/missing'), folder, client=client)
            archive.rate_limit = lambda *args: None
            with self.assertRaises(FetchError):
                archive.run()
            self.assertFalse((Path(folder) / 'archive.zip').exists())

    def test_page_redirect_cannot_leave_hostname(self):
        client = FixtureClient({'https://example.com/': ('https://elsewhere.test/', 'text/html', 'no')})
        with tempfile.TemporaryDirectory() as folder:
            archive = Archive(Options('https://example.com/'), folder, client=client)
            archive.rate_limit = lambda *args: None
            with self.assertRaises(FetchError):
                archive.run()

    def test_css_escaped_urls_and_import(self):
        discovered = []
        result = css_transform(r'@import "nested.css";a{background:url(im\61 ge.png)}', lambda value: discovered.append(value) or 'local/' + value)
        self.assertEqual(discovered, ['nested.css', 'image.png'])
        self.assertIn('local/image.png', result)


class NetworkTests(unittest.TestCase):
    def test_normalize_and_bad_schemes(self):
        self.assertEqual(normalize('../page?q=1#anchor', 'https://EXAMPLE.com:443/a/b'), 'https://example.com/page?q=1')
        for url in ['file:///etc/passwd', 'ftp://example.com', 'http://user:secret@example.com', 'http://example.com:8080/', 'http://example.com/\nsecret', 'http://example.com\\@localhost']:
            with self.subTest(url=url), self.assertRaises(FetchError):
                normalize(url)

    def test_public_dns_blocks_internal_and_mixed_records(self):
        for address in ['127.0.0.1', '10.0.0.1', '169.254.169.254', '192.168.1.1', '100.64.0.1', '0.0.0.0', '::1', 'fc00::1', 'fe80::1', '::ffff:127.0.0.1', '64:ff9b::a00:1', '224.0.0.1', '192.0.0.8', '64:ff9b:1::a00:1', '3fff::1']:
            answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 80))]
            with self.subTest(address=address), patch('socket.getaddrinfo', return_value=answer), self.assertRaises(FetchError):
                public_addresses('example.com', 80)
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 80)) for ip in ['93.184.216.34', '10.0.0.1']]
        with patch('socket.getaddrinfo', return_value=answers), self.assertRaises(FetchError):
            public_addresses('example.com', 80)

    def test_compression_bomb_and_large_body_rejected(self):
        import gzip
        for body, encoding in [(b'x' * 2048, 'identity'), (gzip.compress(b'x' * 100000), 'gzip')]:
            raw = MagicMock()
            raw.status = 200
            raw.getheaders.return_value = [('Content-Encoding', encoding)]
            raw.read.return_value = body
            connection = MagicMock()
            connection.getresponse.return_value = raw
            with patch('webcopy.network.public_addresses', return_value=['93.184.216.34']), patch('http.client.HTTPConnection', return_value=connection), self.assertRaises(FetchError):
                SafeClient('test', max_bytes=1024, retries=0).get('http://example.com/')

    def test_pins_socket_and_rechecks_redirect(self):
        raw = MagicMock()
        raw.status = 302
        raw.getheaders.return_value = [('Location', 'http://127.0.0.1/metadata')]
        raw.read.return_value = b''
        connection = MagicMock()
        connection.getresponse.return_value = raw
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80))]
        def lookup(host, port, **kwargs):
            if host == '127.0.0.1':
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', port))]
            return answers
        with patch('socket.getaddrinfo', side_effect=lookup), patch('http.client.HTTPConnection', return_value=connection) as construct:
            with self.assertRaises(FetchError):
                SafeClient('test', retries=0).get('http://example.com/')
            construct.assert_called_once_with('93.184.216.34', 80, timeout=20)
            self.assertEqual(connection.request.call_args.kwargs['headers']['Host'], 'example.com')


if __name__ == '__main__':
    unittest.main()
