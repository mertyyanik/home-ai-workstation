# Security checklist

- Open WebUI is initially published **only** at `127.0.0.1` on Windows. Do not
  change it to `0.0.0.0` or port-forward it through your home router.
- Ollama's port 11434 is published on `127.0.0.1` only, for local editor tools.
  Ollama has no authentication: any program on this PC can use it, so do not bind
  it to `0.0.0.0` or forward it through Tailscale.
- `WEBUI_SECRET_KEY` is generated locally by `init` into
  `~/.config/home-ai-workstation/aiws.env` on the WSL filesystem (mode `600`),
  outside the project folder, Git and cloud-synced folders. `AIWS_ENV_FILE`
  overrides the path; a pre-existing repository `.env` is still honoured.
- First Open WebUI account should use a strong unique password. Public sign-up
  was off after the first account in the tested build; confirm this in the admin
  settings, because Open WebUI stores this setting in its own database.
- If you later enable remote access, prefer Tailscale Serve and require sign-in;
  don't expose Jupyter, Ollama, or Docker APIs publicly.
- SSH into Ubuntu is key-only, listens on loopback, and is reached through Tailscale
  Serve. Never share a private key, and remove lost devices from the tailnet.
- Never run third-party agent commands with unrestricted host privileges or
  give containers the Docker socket unless you explicitly understand the risks.
- Do not commit private files, notebook outputs, secrets, checkpoints, or datasets.
- Docker named volumes survive `docker compose stop` / `docker compose down`,
  but **not** `docker compose down -v`.
- `aiws backup` output contains `WEBUI_SECRET_KEY` and private chats. It is kept
  unencrypted with owner-only permissions on the same disk. Encrypt any copy you
  move elsewhere, and never put backups in a cloud-synced folder.

- Git ignore rules do not prevent OneDrive/cloud sync. Do not point
  `AIWS_ENV_FILE` at a Windows drive (`/mnt/...`) or a synced folder; `doctor`
  warns when it does.
- Keep local host reports, installer logs and agent handoff notes out of public Git.
