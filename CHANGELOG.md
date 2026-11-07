# Changelog

Versions follow the stages in `docs/ROADMAP.md`. No version has been published yet.

## 0.3.0-dev

### Added
- Key-only SSH into WSL Ubuntu and remote access through Tailscale Serve
- Guidance for Claude Code, Codex and local Ollama models in VS Code
- `pull-recommended` and `version` commands
- Project rules template for ML work
- ShellCheck and PowerShell analysis in CI
- `docs/UPGRADE.md` for testing, applying and rolling back image changes

### Changed
- Ollama API published on `127.0.0.1:11434` for local editor tools
- Ollama context length raised to 16384 after measuring full GPU fit on 8 GB
- Open WebUI pinned to the `v0.13.0` release image, built from the same source commit
  as the earlier pin
- `gpu-test` images pinned to digests

## 0.2.0

### Added
- `backup`, `restore-test` and `restore` commands
- WSL PyTorch and JupyterLab guide with a real GPU check and short training test
- `ml` and `chat` commands to take turns on the GPU

## 0.1.0

### Added
- Ollama and Open WebUI with Docker Compose, GPU access and persistent volumes
- `aiws` CLI for setup, checks, models, status, logs and service control
- Secret file outside the project folder
- Images pinned to tested digests
- CLI fixture tests and CI validation
