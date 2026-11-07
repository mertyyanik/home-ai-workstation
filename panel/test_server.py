"""Tests for the status panel. They need no GPU, Docker or network access.

    python3 -m unittest discover -s panel
"""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


class ParsingTests(unittest.TestCase):
    def test_gpu_line(self):
        result = server.parse_gpu('NVIDIA GeForce RTX 2060 SUPER, 12, 5100, 8192, 58\n')
        self.assertEqual(result['name'], 'NVIDIA GeForce RTX 2060 SUPER')
        self.assertEqual(result['utilization_percent'], 12)
        self.assertEqual(result['memory_used_mib'], 5100)
        self.assertEqual(result['temperature_c'], 58)

    def test_gpu_failure_or_missing_value(self):
        self.assertIsNone(server.parse_gpu(None))
        self.assertIsNone(server.parse_gpu(''))
        self.assertIsNone(server.parse_gpu('name, [N/A], 1, 2, 3'))

    def test_meminfo(self):
        result = server.parse_meminfo('MemTotal: 1000 kB\nMemFree: 1 kB\nMemAvailable: 400 kB\n')
        self.assertEqual(result, {'used_bytes': 600 * 1024, 'total_bytes': 1000 * 1024})
        self.assertIsNone(server.parse_meminfo('MemTotal: 1000 kB\n'))

    def test_loaded_models(self):
        result = server.parse_loaded_models({'models': [
            {'name': 'a:1b', 'size': 200, 'size_vram': 100, 'expires_at': 'x'},
            {'name': 'b:2b'},
        ]})
        self.assertEqual(result[0], {'name': 'a:1b', 'gpu_percent': 50, 'expires_at': 'x'})
        self.assertIsNone(result[1]['gpu_percent'])
        self.assertEqual(server.parse_loaded_models(None), [])

    def test_containers(self):
        self.assertEqual(server.parse_containers('ollama\trunning\nopen-webui\texited\n'),
                         {'ollama': 'running', 'open-webui': 'exited'})
        self.assertEqual(server.parse_containers(None), {})

    def test_service_states(self):
        self.assertEqual(server.service_states(None), ('unknown', 'unknown'))
        self.assertEqual(server.service_states({}), ('missing', 'missing'))
        self.assertEqual(server.service_states({'ollama': 'running'}), ('running', 'missing'))

    def test_host_check(self):
        for host in ('127.0.0.1:8088', 'localhost:8088', 'localhost'):
            self.assertTrue(server.host_allowed(host), host)
        for host in ('evil.example', 'evil.example:8088', '127.0.0.1.evil.example:8088', '', None):
            self.assertFalse(server.host_allowed(host), host)


class BackupTests(unittest.TestCase):
    def test_latest_backup(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(server.latest_backup(root))
            (Path(root) / 'other').mkdir()
            old = Path(root) / 'aiws-backup-1'
            new = Path(root) / 'aiws-backup-2'
            old.mkdir()
            new.mkdir()
            os.utime(old, (1000, 1000))
            os.utime(new, (2000, 2000))
            self.assertEqual(server.latest_backup(root), 2000)

    def test_missing_folder(self):
        self.assertIsNone(server.latest_backup('/nonexistent/aiws'))


class CacheTests(unittest.TestCase):
    def test_reuses_recent_value(self):
        calls = []
        cache = server.Cache(lambda: calls.append(1) or len(calls))
        self.assertEqual(cache.get(), 1)
        self.assertEqual(cache.get(), 1)
        cache.expires = time.monotonic() - 1
        self.assertEqual(cache.get(), 2)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        status = {'time': 1, 'services': {'ollama': 'running'}}
        cache = server.Cache(lambda: status)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(cache))
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, method='GET', host='127.0.0.1'):
        connection = HTTPConnection('127.0.0.1', self.port, timeout=5)
        connection.putrequest(method, path, skip_host=True)
        connection.putheader('Host', host)
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    def test_page(self):
        response, body = self.request('/')
        self.assertEqual(response.status, 200)
        self.assertIn(b'<html', body)
        self.assertEqual(response.getheader('X-Frame-Options'), 'DENY')
        self.assertIn("default-src 'none'", response.getheader('Content-Security-Policy'))

    def test_status(self):
        response, body = self.request('/api/status')
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body)['services']['ollama'], 'running')

    def test_other_host_is_refused(self):
        response, body = self.request('/api/status', host='evil.example')
        self.assertEqual(response.status, 403)
        self.assertNotIn(b'ollama', body)

    def test_unknown_path_and_traversal(self):
        self.assertEqual(self.request('/server.py')[0].status, 404)
        self.assertEqual(self.request('/../server.py')[0].status, 404)

    def test_read_only(self):
        for method in ('POST', 'PUT', 'DELETE'):
            self.assertEqual(self.request('/api/status', method=method)[0].status, 501, method)

    def test_page_has_no_external_resources(self):
        body = (server.HERE / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('http://', body)
        self.assertNotIn('https://', body)
        self.assertNotIn('innerHTML', body)


class BindingTests(unittest.TestCase):
    def test_main_binds_loopback_only(self):
        source = (server.HERE / 'server.py').read_text(encoding='utf-8')
        self.assertIn("ThreadingHTTPServer(('127.0.0.1', args.port)", source)
        self.assertNotIn('0.0.0.0', source)


if __name__ == '__main__':
    unittest.main()
