#!/usr/bin/env python3
"""Status and control panel for Home AI Workstation. Uses the standard library only.

It listens on 127.0.0.1. Once a password is set, every visitor must sign in, including
local ones, because Tailscale Serve also connects from 127.0.0.1. Controls exist only
with a password. They run a fixed list of aiws commands, one at a time, and no request
text ever reaches a command. The panel never reads the env file. Start it with:

    bash scripts/aiws.sh panel
"""
import argparse
import http.cookies
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import auth

HERE = Path(__file__).resolve().parent
LOCAL_HOSTS = {'127.0.0.1', 'localhost'}
COOKIE_NAME = 'aiws_panel'
MAX_BODY_BYTES = 4096
CACHE_SECONDS = 2
ACTION_TIMEOUT_SECONDS = 600
MODEL_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$')
# The only commands the panel can run. Nothing here deletes or restores data.
ACTIONS = {
    'chat': [['chat']],
    'ml': [['ml']],
    'backup': [['backup']],
    'webui_stop': [['webui-stop']],
}
TAILSCALE = '/mnt/c/Program Files/Tailscale/tailscale.exe'
NVIDIA_SMI_FALLBACK = '/usr/lib/wsl/lib/nvidia-smi'
SECURITY_HEADERS = {
    'Cache-Control': 'no-store',
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; "
                               "script-src 'unsafe-inline'; connect-src 'self'; "
                               "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    # With no-referrer, browsers send "Origin: null" on form posts and sign-in fails.
    'Referrer-Policy': 'same-origin',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
}


def run(command, timeout=5):
    """Return a command's standard output, or None if it fails."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def parse_gpu(text):
    """Parse one line of nvidia-smi CSV output, or return None."""
    try:
        name, utilization, used, total, temperature = [
            part.strip() for part in text.strip().splitlines()[0].split(',')]
        return {
            'name': name,
            'utilization_percent': int(utilization),
            'memory_used_mib': int(used),
            'memory_total_mib': int(total),
            'temperature_c': int(temperature),
        }
    except (AttributeError, IndexError, ValueError):
        return None


def gpu():
    command = shutil.which('nvidia-smi') or NVIDIA_SMI_FALLBACK
    return parse_gpu(run([
        command, '--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu',
        '--format=csv,noheader,nounits']))


def parse_meminfo(text):
    """Return used and total memory in bytes from /proc/meminfo text, or None."""
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(':')
        fields = rest.split()
        if fields and fields[0].isdigit():
            values[key] = int(fields[0]) * 1024
    if 'MemTotal' not in values or 'MemAvailable' not in values:
        return None
    return {'used_bytes': values['MemTotal'] - values['MemAvailable'], 'total_bytes': values['MemTotal']}


def memory():
    try:
        return parse_meminfo(Path('/proc/meminfo').read_text(encoding='ascii'))
    except OSError:
        return None


def disk():
    try:
        usage = shutil.disk_usage(Path.home())
    except OSError:
        return None
    return {'free_bytes': usage.free, 'total_bytes': usage.total}


def http_json(url):
    """Return parsed JSON from a local service, or None."""
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def parse_loaded_models(data):
    """Summarize Ollama /api/ps output. Size fields may be missing."""
    models = []
    for model in (data or {}).get('models', []):
        size = model.get('size') or 0
        in_vram = model.get('size_vram') or 0
        models.append({
            'name': model.get('name', ''),
            'gpu_percent': round(in_vram / size * 100) if size else None,
            'expires_at': model.get('expires_at'),
        })
    return models


def parse_containers(text):
    """Return {service: state} from tab-separated docker ps output."""
    states = {}
    for line in (text or '').splitlines():
        service, _, state = line.partition('\t')
        if service:
            states[service] = state
    return states


def containers(project):
    """Return {service: state}, or None when Docker cannot be reached."""
    output = run([
        'docker', 'ps', '--all', '--filter', f'label=com.docker.compose.project={project}',
        '--format', '{{.Label "com.docker.compose.service"}}\t{{.State}}'])
    return None if output is None else parse_containers(output)


def port_answers(port):
    """Return True when a local TCP port accepts a connection."""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def tailscale_state():
    """Return the connection state only; names and addresses stay private."""
    if not os.path.exists(TAILSCALE):
        return 'unknown'
    output = run([TAILSCALE, 'status', '--json'], timeout=4)
    try:
        return 'connected' if json.loads(output).get('BackendState') == 'Running' else 'disconnected'
    except (TypeError, ValueError):
        return 'unknown'


def latest_backup(root):
    """Return the newest backup's time, without its path."""
    try:
        backups = [path for path in Path(root).iterdir()
                   if path.is_dir() and path.name.startswith('aiws-backup-')]
    except OSError:
        return None
    if not backups:
        return None
    return int(max(path.stat().st_mtime for path in backups))


def service_states(states):
    """Tell "Docker is unreachable" apart from "the container does not exist"."""
    fallback = 'unknown' if states is None else 'missing'
    states = states or {}
    return states.get('ollama', fallback), states.get('open-webui', fallback)


def snapshot(config):
    ollama, open_webui = service_states(containers(config['project']))
    loaded = http_json(f"http://127.0.0.1:{config['ollama_port']}/api/ps")
    return {
        'time': int(time.time()),
        'gpu': gpu(),
        'memory': memory(),
        'disk': disk(),
        'models': parse_loaded_models(loaded),
        'services': {
            'ollama': ollama,
            'open_webui': open_webui,
            'ssh': 'listening' if port_answers(config['ssh_port']) else 'closed',
            'tailscale': tailscale_state(),
        },
        'last_backup': latest_backup(config['backup_root']),
    }


def unload_commands(models):
    """Build unload commands from what Ollama reports, never from a request."""
    return [['unload', model['name']] for model in models if MODEL_NAME.match(model.get('name', ''))]


def run_aiws(arguments):
    """Run one aiws command and return its exit code. Output is not exposed."""
    try:
        result = subprocess.run(
            ['bash', 'scripts/aiws.sh', *arguments], cwd=HERE.parent, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=ACTION_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        return 1
    return result.returncode


class Jobs:
    """Run one action at a time in the background and remember how it ended."""

    def __init__(self, runner=run_aiws, on_finish=lambda: None):
        self.runner = runner
        self.on_finish = on_finish
        self.lock = threading.Lock()
        self.current = None

    def status(self):
        with self.lock:
            return dict(self.current) if self.current else None

    def start(self, action, commands):
        """Return False when another action is still running."""
        with self.lock:
            if self.current and self.current['state'] == 'running':
                return False
            self.current = {'action': action, 'state': 'running', 'started': int(time.time())}
        threading.Thread(target=self.work, args=(commands,), daemon=True).start()
        return True

    def work(self, commands):
        state = 'done'
        for command in commands:
            if self.runner(command) != 0:
                state = 'failed'
                break
        with self.lock:
            self.current['state'] = state
            self.current['finished'] = int(time.time())
        self.on_finish()


class Cache:
    """Keep status work bounded when several browser tabs poll at once."""

    def __init__(self, collect):
        self.collect = collect
        self.lock = threading.Lock()
        self.value = None
        self.expires = 0.0

    def get(self):
        with self.lock:
            now = time.monotonic()
            if self.value is None or now >= self.expires:
                self.value = self.collect()
                self.expires = now + CACHE_SECONDS
            return self.value

    def clear(self):
        with self.lock:
            self.expires = 0.0


def host_name(header):
    return header.rsplit(':', 1)[0].lower() if header else ''


def host_allowed(header, extra=()):
    """Block other hosts, which also stops DNS rebinding from web pages."""
    name = host_name(header)
    return name in LOCAL_HOSTS or name in extra


def make_handler(cache, access, jobs, loaded_models=lambda: []):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'aiws-panel'
        sys_version = ''

        def respond(self, status, content_type, body, headers=()):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def text(self, status, message):
            self.respond(status, 'text/plain; charset=utf-8', message.encode())

        def redirect(self, location, headers=()):
            self.respond(303, 'text/plain; charset=utf-8', b'', [('Location', location), *headers])

        def page(self, name):
            self.respond(200, 'text/html; charset=utf-8', (HERE / name).read_bytes())

        def token(self):
            try:
                cookies = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
            except http.cookies.CookieError:
                return None
            cookie = cookies.get(COOKIE_NAME)
            return cookie.value if cookie else None

        def host_ok(self):
            """A remote host needs a password, so a login can never be skipped."""
            header = self.headers.get('Host')
            extra = access.allowed_hosts() if access.required() else ()
            return host_allowed(header, extra)

        def cookie(self, value, max_age):
            parts = [f'{COOKIE_NAME}={value}', 'HttpOnly', 'SameSite=Strict', 'Path=/', f'Max-Age={max_age}']
            if host_name(self.headers.get('Host')) not in LOCAL_HOSTS:
                parts.append('Secure')
            return ('Set-Cookie', '; '.join(parts))

        def signed_in(self):
            return not access.required() or access.valid(self.token())

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if not self.host_ok():
                self.text(403, 'Forbidden host\n')
            elif path == '/login':
                if access.required() and not self.signed_in():
                    self.page('login.html')
                else:
                    self.redirect('/')
            elif path == '/':
                if self.signed_in():
                    self.page('index.html')
                else:
                    self.redirect('/login')
            elif path == '/api/status':
                if self.signed_in():
                    status = {**cache.get(), 'login_required': access.required(),
                              'controls': access.required(), 'job': jobs.status()}
                    self.respond(200, 'application/json', json.dumps(status).encode())
                else:
                    self.text(401, 'Sign in required\n')
            else:
                self.text(404, 'Not found\n')

        def same_origin(self):
            """Browsers send Origin on POST; a mismatch means another site sent the form."""
            origin = self.headers.get('Origin')
            if origin is None:
                return True
            return urllib.parse.urlsplit(origin).hostname == host_name(self.headers.get('Host'))

        def form(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return None
            if length < 0 or length > MAX_BODY_BYTES:
                return None
            data = self.rfile.read(length).decode('utf-8', 'replace')
            return urllib.parse.parse_qs(data, keep_blank_values=True)

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            if not self.host_ok() or not self.same_origin():
                self.text(403, 'Forbidden\n')
            elif path == '/login':
                form = self.form()
                if form is None:
                    self.text(413, 'Too large\n')
                    return
                token, error = access.login(form.get('password', [''])[0])
                if token:
                    self.redirect('/', [self.cookie(token, auth.SESSION_SECONDS)])
                else:
                    self.redirect(f'/login?error={error}')
            elif path == '/logout':
                access.logout(self.token())
                self.redirect('/login', [self.cookie('', 0)])
            elif path == '/api/action':
                self.action()
            else:
                self.text(405, 'Method not allowed\n')

        def action(self):
            """Controls need a password, a session, this site's page and a known name."""
            if not access.required():
                self.text(403, 'Set a panel password first\n')
            elif not access.valid(self.token()):
                self.text(401, 'Sign in required\n')
            elif not self.headers.get('Origin') or self.headers.get('X-AIWS-Action') != '1':
                self.text(403, 'Forbidden\n')
            else:
                self.run_action()

        def run_action(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0 or length > MAX_BODY_BYTES:
                    raise ValueError
                name = json.loads(self.rfile.read(length)).get('action')
            except (AttributeError, ValueError):
                self.text(400, 'Bad request\n')
                return
            if name == 'unload':
                commands = unload_commands(loaded_models())
            else:
                commands = ACTIONS.get(name) if isinstance(name, str) else None
            if not commands:
                self.text(400, 'Unknown action\n')
            elif jobs.start(name, commands):
                self.text(202, 'Started\n')
            else:
                self.text(409, 'Another action is running\n')

        def log_message(self, format, *args):
            return

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8088)
    parser.add_argument('--ollama-port', type=int, default=11434)
    parser.add_argument('--ssh-port', type=int, default=2222)
    parser.add_argument('--project', default='home-ai-workstation')
    parser.add_argument('--backup-root', required=True)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = {'ollama_port': args.ollama_port, 'ssh_port': args.ssh_port,
              'project': args.project, 'backup_root': args.backup_root}
    cache = Cache(lambda: snapshot(config))
    jobs = Jobs(on_finish=cache.clear)

    def loaded_models():
        return parse_loaded_models(http_json(f'http://127.0.0.1:{args.ollama_port}/api/ps'))

    handler = make_handler(cache, auth.Auth(args.config), jobs, loaded_models)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    print(f'Status panel: http://127.0.0.1:{args.port} (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
