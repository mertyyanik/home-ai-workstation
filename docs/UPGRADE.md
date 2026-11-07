# Upgrading images

Images are pinned to digests, so nothing changes until you choose to upgrade. A new
Open WebUI version can migrate its database, and an older image may not be able to read
the result. Test on a copy first, and keep a backup you can return to.

Run these in Ubuntu from the repository root.

## 1. Read and choose

Read the release notes for database changes and required steps. Find the digest of the
version you want, for example:

```bash
docker buildx imagetools inspect ghcr.io/open-webui/open-webui:vX.Y.Z --format '{{.Manifest.Digest}}'
```

The value you need has the form `vX.Y.Z@sha256:DIGEST`.

## 2. Back up

```bash
bash scripts/aiws.sh backup
bash scripts/aiws.sh restore-test BACKUP_DIR
```

## 3. Test on a copy

A separate project name gives you separate containers and volumes, so live data is not
touched. The test Web UI uses port 3199 and starts without Ollama.

```bash
export COMPOSE_PROJECT_NAME=aiws-upgrade-test
export OPEN_WEBUI_PORT=3199
export OPEN_WEBUI_TAG='vX.Y.Z@sha256:DIGEST'
export AIWS_BACKUP_DIR="$(mktemp -d)"
bash scripts/aiws.sh restore BACKUP_DIR
docker compose --env-file ~/.config/home-ai-workstation/aiws.env up -d --no-deps open-webui
```

Wait until the container is healthy, open `http://localhost:3199`, sign in, and check your
chats. Then remove the test project. List the volumes first, and delete only the ones that
start with `aiws-upgrade-test_`:

```bash
docker compose --env-file ~/.config/home-ai-workstation/aiws.env down
docker volume ls -q --filter name=aiws-upgrade-test_
docker volume rm aiws-upgrade-test_open_webui_data aiws-upgrade-test_ollama_data
unset COMPOSE_PROJECT_NAME OPEN_WEBUI_PORT OPEN_WEBUI_TAG AIWS_BACKUP_DIR
```

Never use `docker compose down -v` or `docker volume prune` for this.

## 4. Apply

Change the tag in your env file, `~/.config/home-ai-workstation/aiws.env`. To change the
project's default as well, update `compose.yaml` and `.env.example`. Then run:

```bash
bash scripts/aiws.sh up
bash scripts/aiws.sh status
```

Sign in and send a test message. For an Ollama upgrade, also check that `status` shows the
model on the GPU, and that `unload` releases its memory.

## 5. Roll back

If the new version fails, set the old tag back in your env file. If the database was
migrated, restore the backup taken in step 2 as well:

```bash
bash scripts/aiws.sh up
bash scripts/aiws.sh restore BACKUP_DIR --replace
bash scripts/aiws.sh restart
```

`--replace` overwrites current data after taking a safety backup. Anything created after
the step 2 backup is lost from the live system, but stays in the safety backup.
