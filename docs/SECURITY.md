# Security

Home AI Workstation is built for one person on a trusted personal PC. It is not a
multi-user server, and it should not be exposed to the internet.

## Reporting a problem

Please do not report security problems in a public issue. Use **Report a vulnerability**
under the repository's **Security** tab, and include steps to reproduce the problem.
Report bugs in Ollama, Open WebUI or Tailscale to those projects.

Only the latest version on `main` is supported. This is a personal project, so there is no
guaranteed response time.

## What the design protects against

| Risk | Protection |
| --- | --- |
| Access from the internet or home network | Services bind to `127.0.0.1`; remote access goes only through your Tailscale network |
| Password guessing on SSH | Key-only login, no root login, listens on loopback only |
| Secret leaks through Git or folder sync | Secret lives outside the project folder with owner-only permissions; CI scans Git history |
| Losing chats and settings | `backup`, tested `restore`, encrypted `backup-export` |
| Unplanned image changes | Images pinned to digests; upgrades follow `docs/UPGRADE.md` |

## What it does not protect against

- **Malware or a compromised Windows or Ubuntu account.** Local programs can reach Ollama,
  which has no login, and anything running as your Ubuntu user can read your secret,
  backups and SSH keys.
- **Coding agents.** They run as your user. Rules files guide them but do not stop them.
  Keep approval prompts on, and do not grant full access. Code and files they read go to
  their provider.
- **Physical access.** Backups in the backup folder are not encrypted, and files are only
  as safe as the PC. Consider Windows disk encryption.
- **A compromised Tailscale account.** Anyone in your tailnet can reach the Web UI login
  and SSH port. Protect that account with strong sign-in, and remove lost devices.
- **Open WebUI extensions.** Tools and functions can run code. Install only what you have
  reviewed.

Local inference is not the same as offline. Model downloads, web search and external
providers use the network.

## Rules

- Keep Open WebUI and Ollama on `127.0.0.1`. Do not change them to `0.0.0.0`, and do not
  forward ports through your router.
- Never forward Ollama, Jupyter, the status panel or the Docker API through Tailscale, and
  never use Funnel. The status panel has no login yet.
- Use a strong, unique password for the first Open WebUI account. Sign-up was off after
  the first account in testing. Confirm this in the admin settings.
- Do not give containers the Docker socket, your home folder or SSH keys.
- Keep Jupyter on loopback with token protection on.
- Do not commit private files, notebook outputs, secrets, checkpoints or datasets.

## Secrets and backups

- `init` writes `WEBUI_SECRET_KEY` to `~/.config/home-ai-workstation/aiws.env` on the WSL
  filesystem with mode `600`. `AIWS_ENV_FILE` overrides the path. A pre-existing repository
  `.env` still works.
- `.gitignore` does not stop OneDrive or other sync tools. Do not point `AIWS_ENV_FILE` at
  a Windows drive or synced folder; `doctor` warns when it does.
- `aiws backup` output contains the secret and private chats. It stays unencrypted with
  owner-only permissions on the same disk. Use `backup-export` for a copy on another disk,
  and store its passphrase safely. A lost passphrase cannot be recovered.
- Named volumes survive `docker compose down`, but not `docker compose down -v`.
