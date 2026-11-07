"""Password login for the status panel. Uses the standard library only.

The panel config stores a salted scrypt hash, never the password. Sessions live in
memory, so restarting the panel signs everyone out.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path

SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MEMORY = 64 * 1024 * 1024
MIN_PASSWORD_LENGTH = 12
SESSION_SECONDS = 12 * 3600
MAX_FAILURES = 5
LOCK_SECONDS = 60
HOST_PATTERN = re.compile(r'^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$')


def hash_password(password, salt=None):
    salt = salt if salt is not None else os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                            maxmem=SCRYPT_MEMORY, dklen=32)
    return {'salt': salt.hex(), 'hash': digest.hex()}


def verify_password(password, record):
    try:
        expected = hash_password(password, bytes.fromhex(record['salt']))['hash']
        return hmac.compare_digest(expected, record['hash'])
    except (KeyError, TypeError, ValueError):
        return False


def read_config(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_config(path, config):
    """Write the config atomically, readable only by its owner."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.panel-')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as file:
            json.dump(config, file)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


class Auth:
    """Check passwords, limit failed attempts and track sessions."""

    def __init__(self, path, clock=time.monotonic):
        self.path = path
        self.clock = clock
        self.lock = threading.Lock()
        self.sessions = {}
        self.failures = 0
        self.locked_until = 0.0

    def password_record(self):
        return read_config(self.path).get('password')

    def allowed_hosts(self):
        hosts = read_config(self.path).get('allowed_hosts', [])
        return set(hosts) if isinstance(hosts, list) else set()

    def required(self):
        return bool(self.password_record())

    def login(self, password):
        """Return (token, error). The error is None, 'invalid' or 'locked'."""
        record = self.password_record()
        with self.lock:
            if self.clock() < self.locked_until:
                return None, 'locked'
        if not record or not verify_password(password, record):
            with self.lock:
                self.failures += 1
                if self.failures >= MAX_FAILURES:
                    self.failures = 0
                    self.locked_until = self.clock() + LOCK_SECONDS
            return None, 'invalid'
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.failures = 0
            self.sessions[token] = (self.clock() + SESSION_SECONDS, record['salt'])
        return token, None

    def valid(self, token):
        """A session ends when it expires, or when the password changes."""
        record = self.password_record()
        if not token or not record:
            return False
        with self.lock:
            session = self.sessions.get(token)
            if session is None:
                return False
            expires, salt = session
            if self.clock() >= expires or salt != record.get('salt'):
                del self.sessions[token]
                return False
            return True

    def logout(self, token):
        with self.lock:
            self.sessions.pop(token, None)
