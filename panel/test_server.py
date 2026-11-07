"""Tests for the status panel. They need no GPU, Docker or network access.

    python3 -m unittest discover -s panel
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import auth
import server

PASSWORD = 'correct horse battery'
FAST_SCRYPT = 2 ** 4


def setUpModule():
    """Keep password tests fast. Real settings are checked in test_real_cost."""
    global real_n
    real_n = auth.SCRYPT_N
    auth.SCRYPT_N = FAST_SCRYPT


def tearDownModule():
    auth.SCRYPT_N = real_n


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
        self.assertTrue(server.host_allowed('panel.example:8443', {'panel.example'}))
        self.assertTrue(server.host_allowed('PANEL.example', {'panel.example'}))
        self.assertFalse(server.host_allowed('other.example', {'panel.example'}))


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


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        record = auth.hash_password(PASSWORD)
        self.assertNotIn(PASSWORD, json.dumps(record))
        self.assertTrue(auth.verify_password(PASSWORD, record))
        self.assertFalse(auth.verify_password('wrong', record))

    def test_salt_differs(self):
        self.assertNotEqual(auth.hash_password(PASSWORD), auth.hash_password(PASSWORD))

    def test_bad_record(self):
        for record in (None, {}, {'salt': 'zz', 'hash': 'x'}):
            self.assertFalse(auth.verify_password(PASSWORD, record))

    def test_real_cost(self):
        self.assertGreaterEqual(real_n, 2 ** 15)
        auth.SCRYPT_N = real_n
        try:
            self.assertTrue(auth.verify_password(PASSWORD, auth.hash_password(PASSWORD)))
        finally:
            auth.SCRYPT_N = FAST_SCRYPT

    def test_config_is_private(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'new' / 'panel.json'
            auth.write_config(path, {'a': 1})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(auth.read_config(path), {'a': 1})
            self.assertEqual(os.listdir(path.parent), ['panel.json'])

    def test_broken_config(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'panel.json'
            self.assertEqual(auth.read_config(path), {})
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(auth.read_config(path), {})


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'panel.json'
        auth.write_config(self.path, {'password': auth.hash_password(PASSWORD)})
        self.now = 1000.0
        self.access = auth.Auth(self.path, clock=lambda: self.now)

    def test_login_and_logout(self):
        token, error = self.access.login(PASSWORD)
        self.assertIsNone(error)
        self.assertTrue(self.access.valid(token))
        self.access.logout(token)
        self.assertFalse(self.access.valid(token))

    def test_wrong_and_missing_token(self):
        self.assertEqual(self.access.login('wrong'), (None, 'invalid'))
        self.assertFalse(self.access.valid('made-up'))
        self.assertFalse(self.access.valid(None))

    def test_expiry(self):
        token, _ = self.access.login(PASSWORD)
        self.now += auth.SESSION_SECONDS + 1
        self.assertFalse(self.access.valid(token))

    def test_lockout_blocks_correct_password_then_ends(self):
        for _ in range(auth.MAX_FAILURES):
            self.assertEqual(self.access.login('wrong')[1], 'invalid')
        self.assertEqual(self.access.login(PASSWORD), (None, 'locked'))
        self.now += auth.LOCK_SECONDS + 1
        self.assertIsNotNone(self.access.login(PASSWORD)[0])

    def test_password_change_ends_sessions(self):
        token, _ = self.access.login(PASSWORD)
        auth.write_config(self.path, {'password': auth.hash_password('another long password')})
        self.assertFalse(self.access.valid(token))

    def test_no_password_never_logs_in(self):
        auth.write_config(self.path, {})
        self.assertFalse(self.access.required())
        self.assertIsNone(self.access.login('')[0])


class ToolTests(unittest.TestCase):
    def tool(self, config, *args, stdin=''):
        return subprocess.run(
            [sys.executable, str(server.HERE / 'auth_tool.py'), '--config', str(config), *args],
            input=stdin, capture_output=True, text=True, timeout=30, check=False)

    def test_password_and_host(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'panel.json'
            self.assertNotEqual(self.tool(path, 'allow', 'panel.example').returncode, 0)
            self.assertNotEqual(self.tool(path, 'password', stdin='short\n').returncode, 0)
            self.assertFalse(path.exists())
            result = self.tool(path, 'password', stdin=f'{PASSWORD}\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(PASSWORD, path.read_text(encoding='utf-8'))
            self.assertNotIn(PASSWORD, result.stdout)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(self.tool(path, 'allow', 'Panel.Example').returncode, 0)
            self.assertEqual(self.tool(path, 'allow', 'panel.example').returncode, 0)
            self.assertEqual(auth.read_config(path)['allowed_hosts'], ['panel.example'])
            self.assertNotEqual(self.tool(path, 'allow', 'bad host/x').returncode, 0)


class JobTests(unittest.TestCase):
    def wait(self, jobs):
        for _ in range(200):
            status = jobs.status()
            if status and status['state'] != 'running':
                return status
            time.sleep(0.01)
        self.fail('job did not finish')

    def test_success_runs_commands_in_order(self):
        calls = []
        jobs = server.Jobs(runner=lambda command: calls.append(command) or 0)
        self.assertTrue(jobs.start('unload', [['unload', 'a'], ['unload', 'b']]))
        self.assertEqual(self.wait(jobs)['state'], 'done')
        self.assertEqual(calls, [['unload', 'a'], ['unload', 'b']])

    def test_failure_stops_and_reports(self):
        calls = []
        jobs = server.Jobs(runner=lambda command: calls.append(command) or 3)
        jobs.start('unload', [['one'], ['two']])
        self.assertEqual(self.wait(jobs)['state'], 'failed')
        self.assertEqual(calls, [['one']])

    def test_one_action_at_a_time(self):
        release = threading.Event()
        jobs = server.Jobs(runner=lambda command: release.wait(5) and 0)
        self.assertTrue(jobs.start('ml', [['ml']]))
        self.assertFalse(jobs.start('chat', [['chat']]))
        release.set()
        self.wait(jobs)
        self.assertTrue(jobs.start('chat', [['chat']]))
        self.wait(jobs)

    def test_finish_callback(self):
        finished = threading.Event()
        jobs = server.Jobs(runner=lambda command: 0, on_finish=finished.set)
        jobs.start('ml', [['ml']])
        self.assertTrue(finished.wait(2))

    def test_action_list_is_fixed_and_safe(self):
        self.assertEqual(set(server.ACTIONS), {'chat', 'ml', 'backup', 'webui_stop'})
        for commands in server.ACTIONS.values():
            for command in commands:
                self.assertNotIn(command[0], ('down', 'restore', 'init', 'install', 'pull'))

    def test_unload_names_come_from_ollama_and_are_checked(self):
        models = [{'name': 'qwen3.5:4b'}, {'name': 'a; rm -rf /'}, {'name': '--bad'}, {}]
        self.assertEqual(server.unload_commands(models), [['unload', 'qwen3.5:4b']])


class HttpBase(unittest.TestCase):
    @classmethod
    def start(cls, config):
        cls.folder = tempfile.TemporaryDirectory()
        cls.config = Path(cls.folder.name) / 'panel.json'
        auth.write_config(cls.config, config)
        status = {'time': 1, 'services': {'ollama': 'running'}}
        cache = server.Cache(lambda: status)
        cls.access = auth.Auth(cls.config)
        cls.calls = []
        cls.gate = threading.Event()
        cls.gate.set()

        def runner(command):
            cls.calls.append(command)
            cls.gate.wait(5)
            return 0

        cls.jobs = server.Jobs(runner=runner)
        cls.models = [{'name': 'qwen3.5:4b'}]
        handler = server.make_handler(cache, cls.access, cls.jobs, lambda: cls.models)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.folder.cleanup()

    def request(self, path, method='GET', host='127.0.0.1', headers=(), body=b''):
        connection = HTTPConnection('127.0.0.1', self.port, timeout=5)
        connection.putrequest(method, path, skip_host=True)
        connection.putheader('Host', host)
        for name, value in headers:
            connection.putheader(name, value)
        if body or method == 'POST':
            connection.putheader('Content-Length', str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response, data


class LoginHttpTests(HttpBase):
    @classmethod
    def setUpClass(cls):
        cls.start({'password': auth.hash_password(PASSWORD), 'allowed_hosts': ['panel.example']})

    def setUp(self):
        self.access.failures = 0
        self.access.locked_until = 0.0

    def login(self, password=PASSWORD, host='127.0.0.1', origin=None):
        headers = [('Content-Type', 'application/x-www-form-urlencoded')]
        if origin:
            headers.append(('Origin', origin))
        body = urllib.parse.urlencode({'password': password}).encode()
        return self.request('/login', 'POST', host, headers, body)

    def cookie(self, response):
        return response.getheader('Set-Cookie').split(';')[0]

    def test_local_visit_also_needs_login(self):
        response, _ = self.request('/')
        self.assertEqual((response.status, response.getheader('Location')), (303, '/login'))
        response, body = self.request('/api/status')
        self.assertEqual(response.status, 401)
        self.assertNotIn(b'ollama', body)
        self.assertEqual(self.request('/login')[0].status, 200)

    def test_sign_in_and_out(self):
        response, _ = self.login()
        self.assertEqual((response.status, response.getheader('Location')), (303, '/'))
        header = response.getheader('Set-Cookie')
        self.assertIn('HttpOnly', header)
        self.assertIn('SameSite=Strict', header)
        cookie = ('Cookie', self.cookie(response))
        response, body = self.request('/api/status', headers=[cookie])
        self.assertEqual(response.status, 200)
        self.assertTrue(json.loads(body)['login_required'])
        self.assertEqual(self.request('/', headers=[cookie])[0].status, 200)
        self.request('/logout', 'POST', headers=[cookie])
        self.assertEqual(self.request('/api/status', headers=[cookie])[0].status, 401)

    def test_wrong_password(self):
        response, _ = self.login('wrong password')
        self.assertEqual(response.getheader('Location'), '/login?error=invalid')
        self.assertIsNone(response.getheader('Set-Cookie'))

    def test_lockout_message(self):
        for _ in range(auth.MAX_FAILURES):
            self.login('wrong password')
        response, _ = self.login()
        self.assertEqual(response.getheader('Location'), '/login?error=locked')

    def test_remote_host_gets_secure_cookie(self):
        response, _ = self.login(host='panel.example:8443', origin='https://panel.example:8443')
        self.assertEqual(response.status, 303)
        self.assertIn('Secure', response.getheader('Set-Cookie'))

    def test_local_cookie_works_without_https(self):
        self.assertNotIn('Secure', self.login()[0].getheader('Set-Cookie'))

    def test_unknown_host_is_refused(self):
        self.assertEqual(self.request('/login', host='evil.example')[0].status, 403)
        self.assertEqual(self.login(host='evil.example')[0].status, 403)

    def test_cross_site_post_is_refused(self):
        for origin in ('https://evil.example', 'null'):
            response, _ = self.login(origin=origin)
            self.assertEqual(response.status, 403, origin)
            self.assertIsNone(response.getheader('Set-Cookie'))

    def test_login_page_lets_browsers_send_origin(self):
        # no-referrer makes browsers send "Origin: null", which breaks sign-in.
        response, _ = self.request('/login')
        self.assertEqual(response.getheader('Referrer-Policy'), 'same-origin')

    def test_large_body_is_refused(self):
        headers = [('Content-Type', 'application/x-www-form-urlencoded')]
        response, _ = self.request('/login', 'POST', headers=headers, body=b'a' * (server.MAX_BODY_BYTES + 1))
        self.assertEqual(response.status, 413)

    def test_bad_cookie_is_ignored(self):
        for value in ('aiws_panel=fake', 'broken;;;', 'a"b=c'):
            self.assertEqual(self.request('/api/status', headers=[('Cookie', value)])[0].status, 401)


class ActionHttpTests(HttpBase):
    @classmethod
    def setUpClass(cls):
        cls.start({'password': auth.hash_password(PASSWORD), 'allowed_hosts': ['panel.example']})

    def setUp(self):
        for _ in range(300):
            job = self.jobs.status()
            if not job or job['state'] != 'running':
                break
            time.sleep(0.01)
        self.calls.clear()
        self.gate.set()
        self.access.failures = 0
        self.access.locked_until = 0.0
        body = urllib.parse.urlencode({'password': PASSWORD}).encode()
        response, _ = self.request('/login', 'POST', body=body)
        self.session = ('Cookie', response.getheader('Set-Cookie').split(';')[0])

    def act(self, payload, session=True, origin='http://127.0.0.1', header='1', host='127.0.0.1'):
        headers = [('Content-Type', 'application/json')]
        if session:
            headers.append(self.session)
        if origin:
            headers.append(('Origin', origin))
        if header:
            headers.append(('X-AIWS-Action', header))
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return self.request('/api/action', 'POST', host, headers, body)[0].status

    def settle(self):
        for _ in range(300):
            job = self.jobs.status()
            if job and job['state'] != 'running':
                return job
            time.sleep(0.01)
        self.fail('job did not finish')

    def test_each_action_runs_its_fixed_command(self):
        expected = {'ml': ['ml'], 'chat': ['chat'], 'backup': ['backup'], 'webui_stop': ['webui-stop']}
        for action, command in expected.items():
            self.calls.clear()
            self.assertEqual(self.act({'action': action}), 202, action)
            self.settle()
            self.assertEqual(self.calls, [command])

    def test_unload_uses_the_loaded_model(self):
        self.assertEqual(self.act({'action': 'unload', 'model': 'evil; reboot'}), 202)
        self.settle()
        self.assertEqual(self.calls, [['unload', 'qwen3.5:4b']])

    def test_needs_a_session(self):
        self.assertEqual(self.act({'action': 'ml'}, session=False), 401)
        self.assertEqual(self.calls, [])

    def test_needs_origin_and_custom_header(self):
        self.assertEqual(self.act({'action': 'ml'}, origin=None), 403)
        self.assertEqual(self.act({'action': 'ml'}, header=None), 403)
        self.assertEqual(self.act({'action': 'ml'}, origin='https://evil.example'), 403)
        self.assertEqual(self.calls, [])

    def test_unknown_and_broken_requests(self):
        for payload in ({'action': 'down'}, {'action': 'restore'}, {'action': ['ml']}, {}, [], b'{broken'):
            self.assertEqual(self.act(payload), 400, payload)
        self.assertEqual(self.calls, [])

    def test_one_action_at_a_time(self):
        self.gate.clear()
        self.assertEqual(self.act({'action': 'ml'}), 202)
        self.assertEqual(self.act({'action': 'chat'}), 409)
        self.gate.set()
        self.settle()

    def test_status_reports_job_and_controls(self):
        self.act({'action': 'backup'})
        self.settle()
        _, body = self.request('/api/status', headers=[self.session])
        data = json.loads(body)
        self.assertTrue(data['controls'])
        self.assertEqual(data['job']['action'], 'backup')
        self.assertEqual(data['job']['state'], 'done')


class NoPasswordActionTests(HttpBase):
    @classmethod
    def setUpClass(cls):
        cls.start({})

    def test_controls_are_off_without_a_password(self):
        headers = [('Origin', 'http://127.0.0.1'), ('X-AIWS-Action', '1')]
        response, _ = self.request('/api/action', 'POST', headers=headers, body=b'{"action":"ml"}')
        self.assertEqual(response.status, 403)
        self.assertEqual(self.calls, [])
        self.assertFalse(json.loads(self.request('/api/status')[1])['controls'])


class NoPasswordHostTests(HttpBase):
    @classmethod
    def setUpClass(cls):
        cls.start({'allowed_hosts': ['panel.example']})

    def test_allowed_host_needs_a_password_first(self):
        self.assertEqual(self.request('/api/status', host='panel.example')[0].status, 403)
        self.assertEqual(self.request('/', host='panel.example')[0].status, 403)

    def test_login_page_redirects_locally(self):
        response, _ = self.request('/login')
        self.assertEqual((response.status, response.getheader('Location')), (303, '/'))


class HttpTests(HttpBase):
    @classmethod
    def setUpClass(cls):
        cls.start({})

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
        self.assertEqual(self.request('/api/status', method='POST')[0].status, 405)
        for method in ('PUT', 'DELETE'):
            self.assertEqual(self.request('/api/status', method=method)[0].status, 501, method)

    def test_page_has_no_external_resources(self):
        for name in ('index.html', 'login.html'):
            body = (server.HERE / name).read_text(encoding='utf-8')
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
