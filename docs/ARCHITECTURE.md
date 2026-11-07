# Architecture — ADR-001

## Goal
One Windows computer provides local LLM inference and later ML jobs with an
NVIDIA GPU, usable from other personal devices securely.

```text
MacBook / iPhone (Tailscale)
                |
          HTTPS / SSH
                |
Windows host (NVIDIA driver, Tailscale)
                |
          Docker Desktop + WSL2
                |
  +-------------+---------------+
  |                             |
WSL Ubuntu                      Docker network: ai_internal
Git / Python / Codex             |               |
ML projects                Open WebUI        Ollama (GPU)
                               |                |
                          WebUI volume      models volume
```

## Decisions
- Keep Windows as host and install *Windows* NVIDIA driver; **do not** install
  a separate Linux GPU driver inside WSL.
- Docker Desktop with WSL2 backend is the **only** Docker daemon. Don't install
  a competing Docker Engine in Ubuntu.
- Docker only handles always-available services; ML training uses project-specific
  WSL Python venvs.
- Open WebUI and the Ollama API bind to `127.0.0.1` only. Ollama's port serves local
  editor tools and is never forwarded through Tailscale, because it has no login.
- Tailscale runs on the Windows host only. Serve forwards the Web UI and loopback SSH.
- Use named volumes for model/chat persistence; never commit private datasets.
- Keep one GPU-heavy job at a time for 8 GB VRAM. True resource scheduling is
  a future feature, not claimed in v0.1.
- Docker services remain running; Ollama models leave GPU memory after idle.
  Do not promise automatic Windows sleep or wake in v0.1.

## Known limitations
- Remote access needs the PC on and a signed-in Windows session.
- Chat and heavy ML work take turns on the GPU; this is a manual switch.
- No Colab local runtime yet.
- Images are pinned to tested digests; `docs/UPGRADE.md` covers changing them.
