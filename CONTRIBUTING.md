# Contributing

Keep changes small, include reproduction steps, and never include private prompts,
credentials, datasets or machine-specific details.

## Before you submit a change

Run these from the repository root in Ubuntu:

```bash
bash -n scripts/aiws.sh
bash -n scripts/setup-wsl-ssh.sh
bash scripts/test-aiws.sh
python3 -m py_compile scripts/check-ml.py ml/smoke-train.py
WEBUI_SECRET_KEY=ci_dummy_not_a_real_secret docker compose -f compose.yaml config --quiet
```

Run ShellCheck if you have it. CI runs it, along with PowerShell analysis:

```bash
shellcheck scripts/*.sh
```

`scripts/test-aiws.sh` uses a fake Docker CLI, so it needs no GPU and touches no real
service. Add a test when you change `scripts/aiws.sh`.

## Hardware tests

GitHub-hosted runners cannot test GPU passthrough, model inference, WSL or Tailscale.
Run the affected checks on real hardware and include the results:

- `bash scripts/aiws.sh doctor` and `bash scripts/aiws.sh gpu-test`
- `bash scripts/aiws.sh up`, then a model answer and an unload
- `python scripts/check-ml.py` in an ML environment
- `bash scripts/aiws.sh restore-test BACKUP_DIR` for backup changes

Never test a restore or a volume change against data you care about. Use a separate
`COMPOSE_PROJECT_NAME` instead.

## Changing image versions

Take a backup first. Pin the new digest, repeat the hardware tests, and update
`CHANGELOG.md`. A database migration can prevent a simple rollback to an older image.
