# Third-party software

This repository's own code is MIT licensed. It does not include third-party binaries,
images or model weights. Docker and Ollama download them from their publishers, under
their own licenses. Review those licenses for your use. This page is a summary, not legal
advice. Last reviewed in November 2026.

| Component | How it is used | License |
| --- | --- | --- |
| [Ollama](https://github.com/ollama/ollama) | Official Docker image, pulled at install | MIT |
| [Open WebUI](https://github.com/open-webui/open-webui) | Official Docker image, pulled at install | Open WebUI License |
| `qwen3:4b` | Downloaded by the user through Ollama | Apache 2.0 |
| `qwen2.5-coder:7b` | Downloaded by the user through Ollama | Apache 2.0 |
| NVIDIA CUDA images | Used only by `gpu-test` | NVIDIA terms |
| PyTorch and JupyterLab | Installed by the user, following `ml/README.md` | Their own licenses |
| [Tailscale](https://tailscale.com/) | Optional, installed by the user | Client and service terms |

## Open WebUI branding

The Open WebUI license restricts changing or removing its branding, with exceptions that
include deployments of up to 50 users in a rolling 30-day period. This project uses the
unmodified official image and does not change its branding. If you customize or
redistribute Open WebUI, read its license first.

## Models

A model's license can differ between sizes and tags. Check it before you add a model:

```bash
docker compose --env-file ~/.config/home-ai-workstation/aiws.env exec ollama ollama show --license MODEL
```
