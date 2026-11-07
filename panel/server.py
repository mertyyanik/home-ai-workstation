#!/usr/bin/env python3
"""Read-only status panel for Home AI Workstation. Uses the standard library only.

It listens on 127.0.0.1 and has no login, so it must not be published through
Tailscale. It changes nothing and never reads the env file. Start it with:

    bash scripts/aiws.sh panel
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALLOWED_HOSTS = {'127.0.0.1', 'localhost'}
CACHE_SECONDS = 2
TAILSCALE = '/mnt/c/Program Files/Tailscale/tailscale.exe'
NVIDIA_SMI_FALLBACK = '/usr/lib/wsl/lib/nvidia-smi'
SECURITY_HEADERS = {
    'Cache-Control': 'no-store',
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; "
                               "script-src 'unsafe-inline'; connect-src 'self'",
    'Referrer-Policy': 'no-referrer',
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


def host_allowed(header):
    """Block other hosts, which also stops DNS rebinding from web pages."""
    if not header:
        return False
    return header.rsplit(':', 1)[0] in ALLOWED_HOSTS


def make_handler(cache):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'aiws-panel'
        sys_version = ''

        def respond(self, status, content_type, body):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not host_allowed(self.headers.get('Host')):
                self.respond(403, 'text/plain; charset=utf-8', b'Forbidden host\n')
            elif self.path == '/':
                self.respond(200, 'text/html; charset=utf-8', (HERE / 'index.html').read_bytes())
            elif self.path == '/api/status':
                body = json.dumps(cache.get()).encode()
                self.respond(200, 'application/json', body)
            else:
                self.respond(404, 'text/plain; charset=utf-8', b'Not found\n')

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
    args = parser.parse_args()
    config = {'ollama_port': args.ollama_port, 'ssh_port': args.ssh_port,
              'project': args.project, 'backup_root': args.backup_root}
    cache = Cache(lambda: snapshot(config))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(cache))
    print(f'Status panel: http://127.0.0.1:{args.port} (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
