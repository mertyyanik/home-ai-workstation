#!/usr/bin/env python3
"""Set the panel password, or allow a host name. Run through scripts/aiws.sh."""
import argparse
import getpass
import sys

import auth


def read_password():
    """Prompt on a terminal. Tests and automation send one line on standard input."""
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip('\n')
    first = getpass.getpass('New panel password: ')
    if first != getpass.getpass('Repeat it: '):
        raise SystemExit('ERROR: The passwords do not match; nothing was changed.')
    return first


def set_password(path):
    password = read_password()
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        raise SystemExit(f'ERROR: Use at least {auth.MIN_PASSWORD_LENGTH} characters; nothing was changed.')
    config = auth.read_config(path)
    config['password'] = auth.hash_password(password)
    auth.write_config(path, config)
    print('Panel password saved. Open sessions are signed out.')


def allow_host(path, host):
    host = host.lower()
    if not auth.HOST_PATTERN.match(host):
        raise SystemExit('ERROR: That is not a valid host name.')
    config = auth.read_config(path)
    if not config.get('password'):
        raise SystemExit('ERROR: Set a password first: bash scripts/aiws.sh panel-password')
    hosts = config.get('allowed_hosts', [])
    if host not in hosts:
        config['allowed_hosts'] = [*hosts, host]
        auth.write_config(path, config)
    print(f'Panel allows host: {host}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('password')
    allow = commands.add_parser('allow')
    allow.add_argument('host')
    args = parser.parse_args()
    if args.command == 'password':
        set_password(args.config)
    else:
        allow_host(args.config, args.host)


if __name__ == '__main__':
    main()
