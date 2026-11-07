# Home AI Workstation 🚀

**Windows + WSL2 + Docker + NVIDIA GPU** to run a local LLM web UI today,
then extend the same machine into an AI/ML research workstation.

**Status:** v0.1 starter. On Windows / RTX 2060 SUPER, these passed: Compose
configuration, Docker Desktop WSL2 GPU visibility, a CUDA compute sample,
Ollama + Open WebUI startup, `qwen3:4b` inference fully on GPU, browser chat
through Open WebUI, VRAM release by both manual unload and the 5-minute idle
timeout, account, chat and model persistence across `down` and `up`, and no
Web UI access from the LAN. Ollama and Open WebUI images are pinned to the tested digests
(see `.env.example`); the Open WebUI pin is a `main`-branch build, not a release.
Backup and restore, and a WSL PyTorch and Jupyter environment with a short GPU
training run (see `ml/README.md`), also passed.

## What works in the v0.1 configuration

- Ollama with Nvidia GPU reservation in Docker Compose
- Open WebUI, accessible locally at `http://localhost:3000`
- Persistent Docker volumes for models and conversations
- Auto-unload of idle Ollama model after 5 minutes (`OLLAMA_KEEP_ALIVE`)
- CLI to diagnose, start, pull models, monitor and stop
- Web UI and Ollama API bound to localhost only

**Pending validation / future work:** GPU job scheduling, automatic PC
sleep/wake, Codex remote agent, MLflow, Tailscale, Colab remote kernel.
These are roadmap items — not features that already work.

## 0. Hardware target

- Windows 10/11 compatible with Docker Desktop WSL2
- NVIDIA RTX 2060 Super (8 GB VRAM), 16 GB RAM
- Docker Desktop with WSL2 backend, WSL Ubuntu integration enabled
- Current Windows NVIDIA driver with WSL CUDA support

## 1. Windows PowerShell (run as Admin for installation)

```powershell
nvidia-smi
wsl --install -d Ubuntu
wsl --update
wsl -l -v
```

If Ubuntu already exists, do not reinstall it. Restart Windows if required.
Install Docker Desktop, enable WSL2 backend and Ubuntu integration. Install
NVIDIA driver on **Windows**; do **not** install a Linux NVIDIA driver in WSL.

Optional 16 GB RAM tuning: see `config/.wslconfig.example`, and apply with
`wsl --shutdown` in PowerShell. It is an optional memory cap, not a requirement.

## 2. Ubuntu shell (inside WSL)

```bash
sudo apt update
sudo apt install -y git curl openssl
```

For a Windows-native coding agent, keep one active Windows project folder and
access it from WSL using `/mnt/c/...`. If the agent runs inside WSL, prefer
`~/code/home-ai-workstation`. Choose one location; avoid editing two copies.
Windows-native and WSL-native agent environments are distinct from the Docker backend.

### Where the secret lives

`init` writes the secret-bearing env file **outside the project folder** by
default, at `~/.config/home-ai-workstation/aiws.env` on the WSL filesystem
(directory `700`, file `600`). This keeps it out of Git *and* out of
cloud-synced folders such as OneDrive: `.gitignore` prevents Git tracking,
not folder syncing.

The CLI picks the env file in this order:

1. `AIWS_ENV_FILE`, when set (a relative path is relative to the repository)
2. an existing `.env` in the repository (older installs keep working)
3. `~/.config/home-ai-workstation/aiws.env` (or under `$XDG_CONFIG_HOME`)

`doctor` shows which file is used (never its contents) and warns when it sits
on a Windows drive (`/mnt/...`), inside the project folder, or has loose
permissions. To edit settings such as `DEFAULT_MODEL` or `OPEN_WEBUI_PORT`,
edit that file inside Ubuntu.

### Check and initialize

```bash
cd /path/to/home-ai-workstation
bash scripts/aiws.sh init
bash scripts/aiws.sh doctor
bash scripts/aiws.sh gpu-test
```

The GPU test checks GPU visibility and runs a CUDA nbody compute sample; it pulls test images; this can take time and may require a newer
Windows NVIDIA driver. If GPU passthrough is unavailable, **do not proceed**
with GPU-only Compose setup; first correct Windows/WSL/Docker integration.

### Start the stack

```bash
bash scripts/aiws.sh up
bash scripts/aiws.sh pull qwen3:4b
bash scripts/aiws.sh models
bash scripts/aiws.sh active
```

Open `http://localhost:3000` in **Windows** and create the first WebUI account.
Choose `qwen3:4b` from the model list and ask a test question.

### Unload / stop

```bash
bash scripts/aiws.sh unload qwen3:4b  # Release GPU model memory
bash scripts/aiws.sh stop              # Stop Docker services, keep data
bash scripts/aiws.sh down              # Remove containers, keep named volumes
bash scripts/aiws.sh status            # Containers, loaded models, GPU memory
bash scripts/aiws.sh logs ollama       # Last 100 lines; add -f to follow
```

`up` and `restart` wait up to 180 seconds for the services to become ready and
show recent logs on failure. Set `AIWS_READY_TIMEOUT` to change the limit.

### Back up and restore

```bash
bash scripts/aiws.sh backup                  # Stops Open WebUI for a few seconds
bash scripts/aiws.sh restore-test BACKUP_DIR # Tests a backup; live data is untouched
bash scripts/aiws.sh restore BACKUP_DIR      # Into an empty volume, or a new machine
```

`backup` saves Open WebUI data (accounts, chats, settings) and the env file to
`~/.local/share/home-ai-workstation/backups`, or to `AIWS_BACKUP_DIR`. It is not
a copy on another disk: copy backups elsewhere to survive a disk failure, and
encrypt them first, because they contain the secret.

Ollama models are not included; `models.txt` lists them for `pull`. Open WebUI's
embedding and speech models are also left out and need internet to download
again (about 1 GB in testing).

`restore` refuses to overwrite existing data. `restore BACKUP_DIR --replace`
overwrites it after taking a safety backup. On a new machine it also brings back
the env file; an existing env file is never replaced.

## 3. Common issues

| Symptom | What to check |
| --- | --- |
| `docker` not found in Ubuntu | Docker Desktop Settings > Resources > WSL Integration > Ubuntu |
| `could not select device driver` | NVIDIA driver, Docker WSL2 backend, `gpu-test` |
| Open WebUI not reachable | `docker compose ps`, port 3000 conflict, Desktop running |
| Ollama model missing from UI | `bash scripts/aiws.sh models`, `bash scripts/aiws.sh logs` |
| Out of VRAM | `unload`; smaller model; shorten context; don't train alongside LLM |
| WSL consumes too much RAM | Review optional `.wslconfig.example`, consider upgrading to 32 GB |
| Model forgets earlier text in long chats | Prompts over the 16384-token context limit (`OLLAMA_CONTEXT_LENGTH`) are truncated silently; look for `truncating input prompt` in `logs` |
| `pull` fails with `no such host` | Can be temporary; run the same `pull` again, it resumes |
| First answer takes over a minute | Expected on the first request after the Ollama container is created; later loads took seconds in testing |
| `wsl` errors 1618/1601, Docker "unable to start" | A WSL update may be installing; wait for it to finish, services restart on their own |

## 4. Remote access

Remote access uses [Tailscale](https://tailscale.com/) on the **Windows host only**.
Tailscale advises against also running it inside WSL 2. Nothing is opened to the
internet or the home router, and Serve is limited to your own tailnet. Never use
Funnel for this project.

Install Tailscale on Windows and each client, and sign in with the same account.
Publish the Web UI from Windows PowerShell, and approve HTTPS when asked:

```powershell
tailscale serve --bg 3000
```

For SSH, set up a key-only server in Ubuntu that listens only on `127.0.0.1:2222`:

```bash
sudo bash scripts/setup-wsl-ssh.sh
```

Add your client's **public** key to `~/.ssh/authorized_keys` in Ubuntu, then forward
the port from Windows PowerShell:

```powershell
tailscale serve --bg --tcp=2222 tcp://127.0.0.1:2222
```

On the client, add this to `~/.ssh/config`, using your own device and tailnet name:

```text
Host aiws
  HostName DEVICE.TAILNET.ts.net
  Port 2222
  User YOUR_UBUNTU_USER
  IdentityFile ~/.ssh/aiws_ed25519
  IdentitiesOnly yes
```

Then `ssh aiws` opens Ubuntu, and VS Code Remote-SSH can open your Linux projects.

To use local models in VS Code, install the
[Ollama extension](https://docs.ollama.com/integrations/vscode) in the Remote-SSH window
and pick a model under **Ollama** in Chat. Ollama listens on `127.0.0.1:11434` only.
`qwen2.5-coder:7b` passed a small coding test but did not return structured tool calls,
and `qwen3:4b` did. The 16K context is small for large projects; 32K did not fit fully
on an 8 GB GPU in testing.

**Limits:** the PC must be on and awake. After a Windows restart, Docker Desktop and
Ubuntu start only once a user signs in. Tailscale does not wake a sleeping PC.

## 5. Future layers

- **Codex:** WSL workspace / remote SSH and launch training jobs
- **Research:** MLflow, Qdrant, benchmarks
- **Orchestration:** exclusive GPU job queue, safe auto-sleep/Wake-on-LAN

See `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, and `docs/SECURITY.md`.

## Coding-agent handoff

Both Codex and Claude Code can continue from this folder. Read `AGENTS.md` for
shared boundaries; Claude Code starts with `CLAUDE.md`. Local progress and
machine-specific findings live in the ignored `work/SESSION.md` when present.
Keep that note current after each session. Never commit local reports or secrets.

Windows read-only preflight: `powershell -File scripts/windows-check.ps1`
(or `pwsh -File ...` if PowerShell 7 is installed).
Nonzero exit means at least one prerequisite failed or could not be verified.
A successful static Compose check does not prove Docker GPU or inference works.
No installer or BIOS setting is changed by the check script.

## Source links

- [Docker GPU Compose](https://docs.docker.com/compose/how-tos/gpu-support/)
- [Docker Desktop GPU on Windows](https://docs.docker.com/desktop/features/gpu/)
- [Open WebUI environment](https://docs.openwebui.com/reference/env-configuration/)
- [WSL resource config](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
- [Ollama docs](https://docs.ollama.com/)

## License
MIT — see `LICENSE`.
