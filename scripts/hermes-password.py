"""Set the Hermes sign-in password and the settings this project relies on.

Runs inside the Hermes container as the hermes user. Reads the password from the
first line of stdin, so it never appears in arguments, the environment or logs,
and stores only Hermes' own scrypt hash. Usage: python -c "$(cat this file)" USER
"""
import secrets
import subprocess
import sys

sys.path.insert(0, "/opt/hermes")
from plugins.dashboard_auth.basic import hash_password  # noqa: E402


def get(key):
    result = subprocess.run(["hermes", "config", "get", key], capture_output=True, text=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines[-1].strip() if result.returncode == 0 and lines else ""


def put(key, value):
    subprocess.run(["hermes", "config", "set", key, value], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    password = sys.stdin.readline().rstrip("\n")
    if len(password) < 12:
        sys.exit("ERROR: Use at least 12 characters.")
    put("dashboard.basic_auth.username", sys.argv[1])
    put("dashboard.basic_auth.password_hash", hash_password(password))
    put("dashboard.basic_auth.session_ttl_seconds", "43200")
    # A fixed signing key keeps sessions valid across restarts. Changing the
    # password still ends every session, because the key is bound to it.
    if get("dashboard.basic_auth.secret") in ("", "''", '""'):
        put("dashboard.basic_auth.secret", secrets.token_hex(32))
    # The web app must listen on the container's interface to be reachable
    # through the published loopback port; the password gate covers it.
    put("webapp.enabled", "true")
    put("webapp.host", "0.0.0.0")
    # Never borrow logins from other tools. None are mounted, but stay explicit.
    put("auth.adopt_external_logins", "false")


main()
