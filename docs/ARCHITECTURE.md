# Architecture — ADR-001

## Goal
One Windows computer provides local LLM inference and later ML jobs with an
NVIDIA GPU, usable from other personal devices securely.

```text
MacBook / iPhone (future: Tailscale)
                |
          HTTPS / SSH
                |
Windows host (NVIDIA driver, Tailscale in future)
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
- Docker only handles always-available services; ML training environments are
  project-specific WSL Python venvs are deferred to v0.2.
- The Ollama API has no published port. Open WebUI binds to `127.0.0.1` only.
- Use named volumes for model/chat persistence; never commit private datasets.
- Keep one GPU-heavy job at a time for 8 GB VRAM. True resource scheduling is
  a future feature, not claimed in v0.1.
- Docker services remain running; Ollama models leave GPU memory after idle.
  Do not promise automatic Windows sleep or wake in v0.1.

## Known limitations
- MacBook/iPhone remote access not available until Tailscale Serve is configured.
- No Colab local runtime or Codex remote integration in v0.1.
- Image tags are configurable and default to moving tags; freeze to tested
  release versions/digests before publication/stable deployment.
