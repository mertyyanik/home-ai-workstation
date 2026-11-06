# Contributing

This starter is designed for incremental work. Keep pull requests small, include
reproduction steps, and never include private prompts, credentials or datasets.

Before opening a PR:

```bash
bash -n scripts/aiws.sh
python -m py_compile scripts/check-ml.py
WEBUI_SECRET_KEY=ci_dummy_not_a_real_secret docker compose -f compose.yaml config --quiet
```

Hardware-dependent tests (GPU passthrough, model inference, Windows/WSL) cannot
be fully validated by GitHub-hosted runners and must be run manually.
