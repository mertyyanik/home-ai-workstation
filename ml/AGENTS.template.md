# ML project rules for coding agents

Copy this file to your ML project as `AGENTS.md`, and replace `REPO_PATH` with the path
to this repository in Ubuntu. For Claude Code, also add a `CLAUDE.md` with one line:
`@AGENTS.md`.

These rules guide agents but do not enforce anything. Agents run as your Linux user,
so keep approval prompts on.

## Environment

- Work in WSL Ubuntu and use this project's `.venv`. Do not install into system Python.
- Check the GPU's memory and supported precisions before choosing settings.
- Start with a small batch. System memory is limited too.

## GPU

Chat and ML work take turns on the GPU. Stop Ollama before heavy work and start it
again afterwards:

```bash
cd REPO_PATH && bash scripts/aiws.sh ml
cd REPO_PATH && bash scripts/aiws.sh chat
```

Run `nvidia-smi` first and confirm that no other heavy job is running. Run one heavy
job at a time.

If your agent's sandbox blocks the GPU, keep file work inside the sandbox. Ask the
user to approve each GPU command on its own, and do not widen that approval.

In the Codex sandbox, `nvidia-smi` fails with `GPU access blocked by the operating
system`, `/dev/dxg` is missing and `torch.cuda.is_available()` is `False`. That means
the sandbox, not a broken GPU or driver. Do not install or change drivers; run the same
command again outside the sandbox with the user's approval.

## Long jobs

- Start training in its own session: `tmux new-session -d -s NAME`.
- Use `python -u`, write output to `logs/`, and read progress from there.
- Save regular checkpoints to `checkpoints/`.
- Run a short trial before a long job. Report the time and memory it used.
- After an out-of-memory error, reduce the batch size, resolution or context length.

## Limits

- Do not read `~/.config/home-ai-workstation/`, `~/.local/share/home-ai-workstation/`
  or `~/.ssh`. They hold secrets and backups.
- Do not use `sudo`, change system settings, or delete Docker volumes.
- Do not delete data, upload it, or publish anything without the user's permission.
- Keep `data/`, `checkpoints/`, `logs/` and model files out of Git.
- Record each dataset's source and license. Do not paste sensitive data into a chat.
