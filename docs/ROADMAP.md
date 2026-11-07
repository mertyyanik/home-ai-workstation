# Roadmap

Version names are project stages, not dates. A stage starts only after the
previous stage's exit criteria pass on real hardware.

## v0.1 — Foundation
Exit: first chat, GPU inference, VRAM unload and data persistence verified.

- [x] Windows + WSL2 + Docker Compose architecture
- [x] NVIDIA GPU reservation for Ollama
- [x] Ollama + Open WebUI, persistent named volumes, localhost-only UI
- [x] CLI: init, doctor, gpu-test, up, down, pull, models, active, unload, status, logs, stop, restart
- [x] Bounded readiness wait, disk and port checks, bounded logs, log rotation
- [x] Linux syntax checks and Compose CI validation
- [x] Validate Docker WSL2 GPU visibility and a CUDA compute sample on RTX 2060 SUPER / Windows
- [x] Validate Ollama + Open WebUI startup, CLI model inference and VRAM unload
- [x] Validate chat through the Open WebUI browser interface
- [x] Pin the tested Ollama and Open WebUI image digests
- [x] Account and model survive `down` and `up`
- [x] Web UI and Ollama closed on the LAN address (tested from the host)
- [x] Public sign-up off after the first account
- [x] A saved chat survives `down` and `up`
- [x] Web UI unreachable from another LAN device

## v0.2 — Data safety and ML Lab
Exit: restore verified; real CUDA work, a short training run and a checkpoint.

- [x] Backup and restore commands, with a restore test on a separate volume
- [ ] Encrypted backup copy on another disk
- [x] Per-project WSL Python environment with a compatible CUDA PyTorch wheel
- [x] Real GPU calculation, short training run and verified checkpoint
- [x] JupyterLab on loopback with token protection and a GPU notebook kernel
- [x] Simple manual switch between chat and ML GPU use
- [ ] A real training workload near the 8 GB VRAM and 16 GB RAM limits
- [ ] Colab notebook migration and optional local runtime

## v0.3 — Remote access
Exit: authorized remote use from outside home, the correct WSL context, reboot test.

- [x] Open WebUI over Tailscale Serve for MacBook and iPhone
- [x] VS Code Remote-SSH from MacBook into WSL Ubuntu, from outside the home network
- [x] Remote notebooks on the workstation GPU
- [x] Reboot test: services return on their own after a manual Windows sign-in
- [ ] Local Ollama models in VS Code over Remote-SSH
- [ ] Optional unattended recovery after a Windows restart
- [x] Claude Code and Codex desktop workflows reaching WSL, driven from a phone

## v0.4 — GPU coordination
Exit: conflicting jobs stay controlled and recover after failure.

- [ ] Exclusive GPU lock for chat and ML work
- [ ] Job queue, draining, timeouts and recovery after reboot

## v0.5 — Operations
Exit: job tracking and scheduled backups verified.

- [ ] Usage records, GPU monitoring and logs
- [ ] MLflow experiment tracking, if needed

## v0.6 — Energy
Exit: sleep and wake tested without losing work.

- [ ] Idle policy aware of running jobs
- [ ] Safe sleep; Wake-on-LAN only if the hardware supports it

## Later — Based on need
- [ ] RAG, Qdrant, n8n, model router: each needs a concrete use and resource budget
- [ ] Model benchmark runs (latency, token throughput, quality)

## Public release — Separate decision
Exit: a clean Windows machine installs from GitHub with documented prerequisites.

- [ ] One-command Windows installer; users install Docker Desktop, WSL and the NVIDIA driver
- [ ] Clean-install test on an empty Ubuntu distribution
- [x] Pin Open WebUI to a tested release, with an upgrade and rollback guide
- [x] Pin the GPU test images used by `gpu-test`
- [ ] License review, secret scan, clean examples and documentation
