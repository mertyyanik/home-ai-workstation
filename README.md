# Home AI Workstation

Turn a Windows PC with an NVIDIA GPU into a private AI workstation: local chat, GPU
machine learning, and secure access from your other devices. It runs on Windows, WSL2
and Docker Desktop, and nothing is exposed to the internet.

**Status:** `0.3.0-dev`, an early version. Everything marked as tested below ran on one
PC: Windows 11, RTX 2060 SUPER (8 GB), 16 GB RAM. Other hardware is untested, and
installation on a completely clean system has not been tested yet.

## What you get

| Feature | Details |
| --- | --- |
| Local chat | Open WebUI and Ollama with GPU acceleration, at `http://localhost:3000` |
| Persistent data | Models, accounts and chats survive restarts and container removal |
| Backup and restore | One command each, plus a restore test that leaves live data alone |
| ML environment | PyTorch with CUDA and JupyterLab in WSL Ubuntu |
| Remote access | Web UI and SSH from your own devices through Tailscale |
| Coding agents | Claude Code, Codex and local models in VS Code |

The Web UI and Ollama listen on `127.0.0.1` only. See `docs/SECURITY.md`.

## Requirements

- Windows 10 or 11 with BIOS virtualization enabled
- NVIDIA GPU with a current **Windows** driver. Do not install a Linux NVIDIA driver in WSL
- WSL2 with Ubuntu
- Docker Desktop with the WSL2 backend and Ubuntu integration enabled

Install the prerequisites from Windows PowerShell as Administrator. Skip this if Ubuntu
is already installed, and restart Windows if asked:

```powershell
wsl --install -d Ubuntu
```

## Quick start

Download the project with **Code > Download ZIP** on
[GitHub](https://github.com/mertyyanik/home-ai-workstation), or clone it in Ubuntu:

```bash
git clone https://github.com/mertyyanik/home-ai-workstation.git ~/projects/home-ai-workstation
```

Then run this from the project folder in Windows PowerShell. Administrator rights are not
needed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

It checks Windows, WSL, Docker and free space, then runs a real GPU test, creates your
secret, starts the services and downloads the recommended models. Expect several GB of
downloads. The script stops with a fix when a check fails, and it is safe to run again.

Use `-Distro NAME` for a different Linux distribution, and `-SkipGpuTest` or `-SkipModels`
to skip those steps. To run only the checks, which change nothing:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows-check.ps1
```

Then open `http://localhost:3000` in Windows and create the first account, which becomes
the administrator. Use a strong, unique password. Pick a model and ask a question.

Keep a single copy of the project. Inside Ubuntu you can also run
`bash scripts/aiws.sh install`. If Docker already holds Open WebUI data but no env file
exists, installation stops without changing anything, because a new secret must not be
paired with existing data.

## Everyday commands

```bash
bash scripts/aiws.sh status            # Containers, loaded models, GPU memory
bash scripts/aiws.sh logs ollama       # Last 100 lines; add -f to follow
bash scripts/aiws.sh unload qwen3.5:4b # Release GPU memory, keep the service
bash scripts/aiws.sh ml                # Stop Ollama for heavy ML work
bash scripts/aiws.sh chat              # Start services again
bash scripts/aiws.sh stop              # Stop services, keep containers and data
bash scripts/aiws.sh down              # Remove containers, keep data
```

Run `bash scripts/aiws.sh help` for every command. `up`, `chat` and `restart` wait up to
180 seconds for the services and show recent logs on failure. Set `AIWS_READY_TIMEOUT`
to change that limit.

## Status panel

A small page shows GPU, memory, disk, services, the loaded model and the last backup. With a
password set, it also switches between chat and ML modes, starts and stops Ollama and Open
WebUI, unloads the model and takes a backup. It cannot delete or restore anything, and it
runs only a fixed list of commands, one at a time. Install it once in Ubuntu as a service, so
it starts with Ubuntu, then open `http://localhost:8088` in Windows:

```bash
sudo bash scripts/setup-panel-service.sh
```

To run it only for now, use `bash scripts/aiws.sh panel`. Set `AIWS_PANEL_PORT` to change
the port. It listens on `127.0.0.1`. Without a password it is read-only.

Set a password before you use it from other devices. After that, every visitor must sign
in, including on this PC. Then publish it to your own Tailscale network from Windows
PowerShell, which refuses to run without a password:

```bash
bash scripts/aiws.sh panel-password
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-remote.ps1 -Panel
```

It prints the private address. Five wrong passwords lock sign-in for 60 seconds, and a
session lasts 12 hours.

## Local models

`pull-recommended` downloads `qwen3.5:4b` and `qwen2.5-coder:7b`. The table comes from a
small test on an 8 GB GPU at 16K context, so treat it as a starting point, not a benchmark.

| Model | Best for | GPU fit | VRAM | Tokens/s | Structured tool calls |
| --- | --- | --- | --- | --- | --- |
| `qwen3.5:4b` | General chat and tool-using tasks | Full | About 5 GB | 71 | Yes |
| `gemma4:e2b` | Fast answers | Full | About 4.1 GB | 135 | Yes |
| `qwen2.5-coder:7b` | Writing code in chat | Full | About 6 GB | 63 | No |
| `qwen3.5:9b` | Slower answers from a larger model | 84% | About 7 GB | 27 | Yes |

Set `AIWS_MODELS` to choose a different list. Only one model loads at a time, and it
leaves GPU memory after 5 idle minutes. A 32K context did not fit fully on 8 GB.

## Secrets and settings

`init` creates `~/.config/home-ai-workstation/aiws.env` with a random secret. It lives
outside the project folder, because `.gitignore` stops Git but not folder sync tools such
as OneDrive. Edit that file in Ubuntu to change settings such as `DEFAULT_MODEL` or
`OPEN_WEBUI_PORT`.

The CLI uses the first env file it finds:

1. `AIWS_ENV_FILE`, when set; a relative path is relative to the repository
2. An existing `.env` in the repository, so older installs keep working
3. `~/.config/home-ai-workstation/aiws.env`, or under `$XDG_CONFIG_HOME`

`doctor` shows which file is in use, never its contents. It warns about a risky location
or loose permissions.

## Backup and restore

```bash
bash scripts/aiws.sh backup                  # Stops Open WebUI for a few seconds
bash scripts/aiws.sh restore-test BACKUP_DIR # Tests a backup; live data is untouched
bash scripts/aiws.sh restore BACKUP_DIR      # Into an empty volume or a new machine
```

`backup` saves accounts, chats, settings and the env file to
`~/.local/share/home-ai-workstation/backups`, or to `AIWS_BACKUP_DIR`. These stay on the
same disk, unencrypted, and contain the secret. To survive a disk failure, export an
encrypted copy to another disk, such as drive `D:`. It asks for a passphrase, and a lost
passphrase cannot be recovered:

```bash
bash scripts/aiws.sh backup-export BACKUP_DIR /mnt/d/aiws-backup.gpg
bash scripts/aiws.sh backup-import /mnt/d/aiws-backup.gpg
```

Ollama models are not included; `models.txt` lists them. Open WebUI's embedding and
speech models are also left out and download again, about 1 GB in testing.

`restore` refuses to overwrite existing data. `restore BACKUP_DIR --replace` overwrites it
after taking a safety backup. On a new machine it also restores the env file, but it
never replaces an existing one.

## Machine learning

See `ml/README.md` for the environment, GPU checks, notebooks and coding agents. Chat and
heavy ML work take turns on the GPU, so run `aiws ml` first and `aiws chat` afterwards.

## Remote access

Remote access uses [Tailscale](https://tailscale.com/) on the **Windows host only**.
Tailscale advises against also running it inside WSL 2. Nothing opens on the internet or
your router, and Serve is limited to your own tailnet. Never use Funnel for this project.

Install Tailscale on Windows and each client, and sign in with the same account. Publish
the Web UI from Windows PowerShell, and approve HTTPS when asked. The script prints your
private address and is safe to run again:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-remote.ps1
```

For SSH, first set up a key-only server in Ubuntu that listens only on `127.0.0.1:2222`:

```bash
sudo bash scripts/setup-wsl-ssh.sh
```

Then run the remote script with `-Ssh`. It forwards the port and prints the
`~/.ssh/config` entry for your client:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-remote.ps1 -Ssh
```

Add your client's **public** key to `~/.ssh/authorized_keys` in Ubuntu. Then `ssh aiws`
opens Ubuntu, and VS Code Remote-SSH can open your Linux projects.

To use local models in VS Code, install the
[Ollama extension](https://docs.ollama.com/integrations/vscode) in the Remote-SSH window
and pick a model under **Ollama** in Chat.

**Limits:** the PC must be on and awake. After a Windows restart, Docker Desktop and Ubuntu
start only once a user signs in. Tailscale does not wake a sleeping PC.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `docker` not found in Ubuntu | Docker Desktop > Settings > Resources > WSL Integration > Ubuntu |
| `could not select device driver` | NVIDIA driver, Docker WSL2 backend, `gpu-test` |
| Open WebUI not reachable | `status`, a port 3000 conflict, Docker Desktop running |
| Model missing from the UI | `models`, then `logs ollama` |
| Out of VRAM | `unload`, a smaller model or context; don't train alongside a model |
| WSL uses too much RAM | Optional `config/.wslconfig.example`, then `wsl --shutdown` |
| Model forgets earlier text | Prompts over 16384 tokens are cut silently; look for `truncating input prompt` in `logs ollama` |
| `pull` fails with `no such host` | Can be temporary; run the same `pull` again, it resumes |
| First answer takes over a minute | Expected after the Ollama container is created; later loads took seconds |
| `wsl` errors 1618/1601, Docker "unable to start" | A WSL update may be installing; wait, services return on their own |

## Project documents

- `docs/ARCHITECTURE.md`: design decisions and known limits
- `docs/ROADMAP.md`: stages and what is verified
- `docs/SECURITY.md`: access, secrets and backups
- `docs/UPGRADE.md`: changing image versions safely
- `docs/THIRD_PARTY.md`: third-party software and licenses
- `CHANGELOG.md`: changes by version
- `CONTRIBUTING.md`: tests and hardware checks
- `AGENTS.md` and `CLAUDE.md`: rules for coding agents working on this repository; optional
  local notes go in the ignored `AGENTS.local.md` and `CLAUDE.local.md`

## Source links

- [Docker GPU Compose](https://docs.docker.com/compose/how-tos/gpu-support/)
- [Docker Desktop GPU on Windows](https://docs.docker.com/desktop/features/gpu/)
- [Open WebUI environment](https://docs.openwebui.com/reference/env-configuration/)
- [WSL resource config](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
- [Ollama docs](https://docs.ollama.com/)
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)

## License

MIT, see `LICENSE`. Third-party software and models have their own licenses.
