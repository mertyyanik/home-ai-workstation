# Agent rules

Rules for coding agents working on this repository. Read `README.md` first. If
`AGENTS.local.md` exists, read and follow it too. It holds this machine's local notes and
preferences, and it is not committed.

## Scope

- The target is Windows, WSL2, Docker Desktop and an NVIDIA GPU, with Ollama and Open WebUI.
- Keep Open WebUI and Ollama on `127.0.0.1`. Ollama has no authentication, so never expose
  it on the LAN or through Tailscale.
- Check the current state before you act, and do not repeat setup blindly.
- Base your conclusions on real output. Being installed is not the same as working.
- Do not push, publish, or create repositories or pull requests unless the user asks.

## Safety

- Ask for explicit approval before admin installs, BIOS or UEFI changes, restarts and
  destructive actions. Approval for one action does not cover the next.
- Never delete volumes, run `down -v` or prune, unregister WSL distributions, reset data, or
  overwrite an env file or secret on your own initiative.
- Do not read or print secret values, and keep them out of chats, logs and reports. Never
  use the user's passwords or enter them for the user.
- Docker Desktop is the only Docker engine. Do not install a second Docker Engine or a Linux
  NVIDIA driver in Ubuntu.
- `.gitignore` does not stop folder sync tools. Keep secrets outside cloud-synced folders.
- Test risky changes on a separate `COMPOSE_PROJECT_NAME`, never on live data.

## Repository

- Keep the structure of `compose.yaml`, `scripts/`, `config/`, `docs/`, `ml/` and CI.
- Keep a single active copy of the project.
- `.env`, `work/`, `outputs/`, logs, models, data and local agent files stay out of Git.
- Pin images only after testing them on hardware, and do not present untested versions as
  verified. See `docs/UPGRADE.md`.

## Validation

- Windows: `powershell -File scripts/windows-check.ps1`
- CLI changes: `bash scripts/test-aiws.sh` (fake Docker, touches no real service)
- Ubuntu: `bash -n scripts/aiws.sh`, `bash scripts/aiws.sh doctor`,
  `bash scripts/aiws.sh gpu-test`
- Schema check without a real secret: set a temporary `WEBUI_SECRET_KEY`, then run
  `docker compose -f compose.yaml config --quiet`. Never print the resolved config.
- After starting services, verify health, model inference and VRAM unload separately.
- Keep verified, shareable behavior in `README.md` and `docs/`.
