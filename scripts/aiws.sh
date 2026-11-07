#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Location of the secret-bearing env file, in priority order:
#   1. AIWS_ENV_FILE, when set (a relative path is relative to the repository)
#   2. a legacy .env in the repository, when it already exists
#   3. a per-user file outside the repository, so secrets stay out of
#      cloud-synced project folders (OneDrive etc.) and out of Git
DEFAULT_ENV_FILE="${XDG_CONFIG_HOME:-${HOME:?HOME is not set}/.config}/home-ai-workstation/aiws.env"
if [[ -n "${AIWS_ENV_FILE:-}" ]]; then
  ENV_FILE="$AIWS_ENV_FILE"
elif [[ -e .env ]]; then
  ENV_FILE=.env
else
  ENV_FILE="$DEFAULT_ENV_FILE"
fi

# Backups hold the secret, so they default to a per-user folder outside the project.
BACKUP_ROOT="${AIWS_BACKUP_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/home-ai-workstation/backups}"
WEBUI_DATA=/app/backend/data

help() {
  cat <<'EOF'
Home AI Workstation — CLI (run inside WSL Ubuntu)

  bash scripts/aiws.sh init               Create the env file with a random secret
  bash scripts/aiws.sh doctor             Check Docker, env file, disk space and port
  bash scripts/aiws.sh gpu-test           Verify GPU visibility and run a CUDA compute test
  bash scripts/aiws.sh up                 Start Ollama + Open WebUI and wait until ready
  bash scripts/aiws.sh pull [model]       Download a model (default: qwen3:4b)
  bash scripts/aiws.sh models             List downloaded models
  bash scripts/aiws.sh active             Show models currently loaded in memory
  bash scripts/aiws.sh unload [model]     Release an active model from VRAM
  bash scripts/aiws.sh status             Show containers, loaded models and GPU memory
  bash scripts/aiws.sh logs [-f] [service]  Show the last 100 log lines; -f follows
  bash scripts/aiws.sh stop               Stop services; keep containers and volumes
  bash scripts/aiws.sh down               Remove containers; keep named volumes
  bash scripts/aiws.sh restart            Restart services and wait until ready
  bash scripts/aiws.sh ml                 Stop Ollama to free the GPU for ML work
  bash scripts/aiws.sh chat               Start services again after ML work
  bash scripts/aiws.sh backup            Back up Open WebUI data and the env file
  bash scripts/aiws.sh restore-test DIR   Test a backup in a temporary volume
  bash scripts/aiws.sh restore DIR [--replace]  Restore a backup into Open WebUI

backup briefly stops Open WebUI. Ollama models are not included; models.txt lists
them for downloading again. Open WebUI's cached embedding and speech models are
also left out and download again when needed. restore refuses to replace existing
data unless --replace is given, and then takes a safety backup first.

AIWS_READY_TIMEOUT sets the readiness wait in seconds (default: 180).
AIWS_BACKUP_DIR sets the backup folder
(default: ~/.local/share/home-ai-workstation/backups).

Env file: $AIWS_ENV_FILE if set; otherwise an existing repository .env;
otherwise ~/.config/home-ai-workstation/aiws.env (outside the project folder).

Open WebUI and the Ollama API are bound to localhost only.
EOF
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo 'ERROR: docker CLI not found. Install Docker Desktop and enable WSL Integration.' >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo 'ERROR: Docker Compose V2 not found.' >&2
    exit 1
  fi
}

require_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Missing env file ($ENV_FILE). Run: bash scripts/aiws.sh init" >&2
    exit 1
  fi
  if ! grep -Eq '^WEBUI_SECRET_KEY=[a-f0-9]{64}$' "$ENV_FILE"; then
    echo "ERROR: Invalid WEBUI_SECRET_KEY in $ENV_FILE; expected generated 64-char hex value." >&2
    exit 1
  fi
}

# Print the first value of KEY from the env file (empty if absent).
env_value() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  sed -n "/^${key}=/{s/^${key}=//;s/\r\$//;p;q;}" "$ENV_FILE"
}

default_model() {
  local model
  model="$(env_value DEFAULT_MODEL)"
  echo "${model:-qwen3:4b}"
}

compose() {
  docker compose --env-file "$ENV_FILE" "$@"
}

webui_port() {
  local port
  port="$(env_value OPEN_WEBUI_PORT)"
  echo "${port:-3000}"
}

service_running() {
  [[ -n "$(compose ps -q --status running "$1" 2>/dev/null)" ]]
}

# Wait, within a time limit, until Ollama answers and Open WebUI reports healthy.
wait_ready() {
  local timeout="${AIWS_READY_TIMEOUT:-180}" deadline webui health
  deadline=$((SECONDS + timeout))
  echo "Waiting for services (up to ${timeout}s)..."
  while ((SECONDS < deadline)); do
    webui="$(compose ps -q open-webui 2>/dev/null || true)"
    health=''
    if [[ -n "$webui" ]]; then
      health="$(docker inspect -f '{{.State.Health.Status}}' "$webui" 2>/dev/null || true)"
    fi
    if [[ "$health" == healthy ]] && compose exec -T ollama ollama list >/dev/null 2>&1; then
      echo 'OK: Ollama and Open WebUI are ready.'
      return 0
    fi
    sleep 2
  done
  echo "ERROR: Services were not ready within ${timeout}s." >&2
  compose ps >&2 || true
  compose logs --tail=30 >&2 || true
  return 1
}

# Warn (never fail) when free space is low. Arguments: label, free KiB.
report_disk() {
  local free_gib=$(($2 / 1024 / 1024))
  echo "Disk free ($1): ${free_gib} GiB"
  if ((free_gib < 20)); then
    echo "WARNING: less than 20 GiB free for $1; models and images need space." >&2
  fi
}

# Warn (never fail) when another program already uses the Open WebUI port.
check_port() {
  local port
  port="$(webui_port)"
  if timeout 2 bash -c ": </dev/tcp/127.0.0.1/$port" 2>/dev/null; then
    if service_running open-webui; then
      echo "OK: port $port is served by Open WebUI."
    else
      echo "WARNING: port $port is already in use; Open WebUI cannot start on it." >&2
    fi
  else
    echo "OK: port $port is free."
  fi
}

# Warn (never fail) about env file locations or permissions that may leak the secret.
check_env_location() {
  local path mode
  path="$(realpath -m -- "$ENV_FILE")"
  case "$path" in
    /mnt/*)
      echo 'WARNING: env file is on a Windows drive; it may be cloud-synced and Linux' >&2
      echo '         permissions may not be enforced. Prefer a WSL path (see README).' >&2
      ;;
  esac
  case "$path" in
    "$REPO_DIR"/*)
      echo 'NOTE: env file is inside the project folder; keep it Git-ignored and' >&2
      echo '      remember that folder sync tools ignore .gitignore.' >&2
      ;;
  esac
  if [[ -f "$path" ]]; then
    mode="$(stat -c '%a' -- "$path")"
    if [[ "$mode" != 600 && "$mode" != 400 ]]; then
      echo "WARNING: env file permissions are $mode; expected 600 (chmod 600 \"$path\")." >&2
    fi
  fi
}

init() (
  if [[ -e "$ENV_FILE" ]]; then
    echo "Already initialized ($ENV_FILE exists). Won't replace your secret."
    return
  fi
  command -v openssl >/dev/null 2>&1 || {
    echo 'ERROR: openssl is missing. Run: sudo apt install openssl' >&2
    exit 1
  }
  # Restrict access before creating any secret-bearing file or directory.
  # Publish atomically via a hard link from a temporary file in the same
  # directory, refusing to replace an env file created in the meantime.
  umask 077
  local directory temporary secret
  directory="$(dirname -- "$ENV_FILE")"
  mkdir -p -- "$directory"
  temporary="$(mktemp "$directory/.aiws-env.init.XXXXXX")"
  trap 'rm -f -- "$temporary"' EXIT
  secret="$(openssl rand -hex 32)"
  sed -e 's/\r$//' -e "s/^WEBUI_SECRET_KEY=.*/WEBUI_SECRET_KEY=${secret}/" .env.example > "$temporary"
  ln -- "$temporary" "$ENV_FILE"
  echo "Initialized $ENV_FILE with a random secret."
  check_env_location
)

# Run one command in a throwaway Open WebUI container: data volume, no ports, no GPU.
webui_tool() {
  compose run --rm --no-deps -T --entrypoint "$1" open-webui "${@:2}"
}

webui_image() {
  compose config --images | grep -F open-webui | head -1
}

# Stop unless DIR is a complete backup whose checksums match.
verify_backup() {
  local directory="$1" file
  if [[ ! -d "$directory" ]]; then
    echo "ERROR: Backup folder not found: $directory" >&2
    exit 1
  fi
  for file in open-webui-data.tar.gz aiws.env SHA256SUMS; do
    if [[ ! -f "$directory/$file" ]]; then
      echo "ERROR: Incomplete backup; missing $file." >&2
      exit 1
    fi
  done
  if ! (cd "$directory" && sha256sum --check --quiet SHA256SUMS); then
    echo 'ERROR: Backup checksum failed; the backup is damaged.' >&2
    exit 1
  fi
}

backup() (
  umask 077
  local final temporary restart_webui=0 archive
  case "$(realpath -m -- "$BACKUP_ROOT")" in
    /mnt/*) echo 'WARNING: backup folder is on a Windows drive; backups contain the secret.' >&2 ;;
  esac
  mkdir -p -- "$BACKUP_ROOT"
  final="$BACKUP_ROOT/aiws-backup-$(date -u +%Y%m%d-%H%M%S)"
  temporary="$(mktemp -d "$BACKUP_ROOT/.incomplete.XXXXXX")"
  archive="$temporary/open-webui-data.tar.gz"
  # Always remove partial output and bring Open WebUI back, even after a failure.
  finish() {
    rm -rf -- "$temporary"
    if ((restart_webui)); then
      compose start open-webui >/dev/null 2>&1 || echo 'ERROR: Could not restart Open WebUI.' >&2
    fi
  }
  trap finish EXIT

  : > "$temporary/models.txt"
  if service_running ollama; then
    compose exec -T ollama ollama list > "$temporary/models.txt"
  fi
  {
    echo "created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    compose config --images
  } > "$temporary/manifest.txt"
  cp -- "$ENV_FILE" "$temporary/aiws.env"

  # A stopped service keeps the database consistent while it is copied.
  if service_running open-webui; then
    restart_webui=1
    compose stop open-webui >/dev/null 2>&1
  fi
  # Embedding and speech models are large and Open WebUI downloads them again.
  webui_tool tar -C "$WEBUI_DATA" --exclude=./cache/embedding --exclude=./cache/whisper \
    -czf - . > "$archive"
  if ((restart_webui)); then
    compose start open-webui >/dev/null 2>&1
    restart_webui=0
  fi

  if ! gzip -t "$archive" || ! tar -tzf "$archive" | grep -x './webui.db' >/dev/null; then
    echo 'ERROR: Backup archive is invalid or has no Open WebUI database.' >&2
    exit 1
  fi
  (cd "$temporary" && sha256sum open-webui-data.tar.gz aiws.env models.txt manifest.txt > SHA256SUMS)
  mv -T -- "$temporary" "$final"
  echo "Backup created: $final"
  echo "Archive size: $(du -h "$final/open-webui-data.tar.gz" | cut -f1)"
  echo 'It contains the secret. Downloaded models are not included; see models.txt.'
)

restore_test() (
  local directory="$1" volume image
  verify_backup "$directory"
  image="$(webui_image)"
  volume="aiws-restore-test-$(date -u +%Y%m%d-%H%M%S)-$$"
  trap 'docker volume rm -f "$volume" >/dev/null 2>&1 || true' EXIT
  docker volume create "$volume" >/dev/null
  docker run --rm -i -v "$volume:/restore" --entrypoint tar "$image" -xzf - -C /restore \
    < "$directory/open-webui-data.tar.gz"
  docker run --rm -v "$volume:/restore" --entrypoint python3 "$image" -c '
import sqlite3
db = sqlite3.connect("file:/restore/webui.db?mode=ro", uri=True)
print("integrity=" + db.execute("pragma integrity_check").fetchone()[0])
for table in ("user", "chat"):
    count = db.execute("select count(*) from \"" + table + "\"").fetchone()[0]
    print(table + "s=" + str(count))
'
  echo 'OK: Backup restored into a temporary volume; live data was not touched.'
)

restore() (
  umask 077
  local directory="$1" option="${2:-}" state restart_webui=0
  if [[ -n "$option" && "$option" != --replace ]]; then
    echo "ERROR: Unknown option: $option" >&2
    exit 2
  fi
  verify_backup "$directory"

  # On a new machine the backup also brings back the secret. An existing env
  # file is never replaced; a different secret only produces a warning.
  if [[ ! -e "$ENV_FILE" ]]; then
    mkdir -p -- "$(dirname -- "$ENV_FILE")"
    cp -n -- "$directory/aiws.env" "$ENV_FILE"
    echo "Restored env file: $ENV_FILE"
  elif [[ "$(grep '^WEBUI_SECRET_KEY=' "$ENV_FILE")" != "$(grep '^WEBUI_SECRET_KEY=' "$directory/aiws.env")" ]]; then
    echo 'WARNING: backup secret differs from the current env file; users may need to sign in again.' >&2
  fi
  require_env

  state="$(webui_tool sh -c "if [ -e $WEBUI_DATA/webui.db ]; then echo present; else echo absent; fi" | tail -1)"
  case "$state" in
    present)
      if [[ "$option" != --replace ]]; then
        echo 'ERROR: Open WebUI already has data. Use --replace to overwrite it.' >&2
        exit 1
      fi
      echo 'Taking a safety backup of the current data...'
      backup
      ;;
    absent) ;;
    *)
      echo 'ERROR: Could not inspect the Open WebUI volume; nothing was changed.' >&2
      exit 1
      ;;
  esac

  if service_running open-webui; then
    restart_webui=1
    compose stop open-webui >/dev/null 2>&1
  fi
  trap 'if ((restart_webui)); then compose start open-webui >/dev/null 2>&1 || true; fi' EXIT
  webui_tool sh -c "find $WEBUI_DATA -mindepth 1 -delete"
  webui_tool tar -xzf - -C "$WEBUI_DATA" < "$directory/open-webui-data.tar.gz"
  echo "Restored Open WebUI data from: $directory"
)

case "${1:-help}" in
  init) init ;;
  doctor)
    require_docker
    docker version >/dev/null || { echo 'ERROR: Docker Desktop daemon unavailable.' >&2; exit 1; }
    echo 'OK: Docker Desktop daemon and Docker Compose are reachable.'
    echo "OS: $(uname -s)"
    echo "Architecture: $(uname -m)"
    echo "Env file: $ENV_FILE"
    report_disk 'WSL home' "$(df -Pk "$HOME" | awk 'NR==2 {print $4}')"
    if [[ -f "$ENV_FILE" ]]; then
      require_env
      check_env_location
      compose config -q
      echo 'OK: Compose configuration and env file are valid.'
      check_port
      if service_running ollama; then
        report_disk 'Ollama models' "$(compose exec -T ollama df -Pk /root/.ollama | awk 'NR==2 {print $4}')"
      fi
    else
      echo 'Tip: run init to generate the env file, then run doctor again.'
    fi
    ;;
  gpu-test)
    require_docker
    echo 'Testing GPU passthrough with CUDA 12.4 test image...'
    docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
    echo 'Running the Docker-documented CUDA nbody compute test...'
    docker run --rm --gpus all nvcr.io/nvidia/k8s/cuda-sample:nbody nbody -gpu -benchmark
    ;;
  up|chat)
    require_docker; require_env
    compose up -d
    wait_ready
    echo "Open WebUI (local only): http://localhost:$(webui_port)"
    ;;
  ml)
    require_docker; require_env
    # Stopping the service, not only unloading, keeps a new chat from reloading a model.
    compose stop ollama
    echo 'Ollama stopped; chat is unavailable until: bash scripts/aiws.sh chat'
    if command -v nvidia-smi >/dev/null 2>&1; then
      echo "GPU memory (used, total): $(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader)"
    fi
    ;;
  pull)
    require_docker; require_env
    compose exec -T ollama ollama pull "${2:-$(default_model)}"
    ;;
  models)
    require_docker; require_env
    compose exec -T ollama ollama list
    ;;
  active)
    require_docker; require_env
    compose exec -T ollama ollama ps
    ;;
  unload)
    require_docker; require_env
    compose exec -T ollama ollama stop "${2:-$(default_model)}"
    ;;
  status)
    require_docker; require_env
    compose ps
    if service_running ollama; then
      echo
      echo 'Loaded models:'
      compose exec -T ollama ollama ps
      echo
      echo 'GPU memory (used, total):'
      compose exec -T ollama nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
    else
      echo 'Ollama is not running.'
    fi
    echo
    echo "Open WebUI (local only): http://localhost:$(webui_port)"
    ;;
  logs)
    require_docker; require_env
    shift
    follow=()
    if [[ "${1:-}" == -f ]]; then
      follow=(-f)
      shift
    fi
    compose logs --tail=100 "${follow[@]}" "$@"
    ;;
  stop)
    require_docker; require_env
    compose stop
    ;;
  down)
    require_docker; require_env
    # Never add -v here: named volumes hold models, accounts and chats.
    compose down
    echo 'Containers removed. Named volumes (models, accounts, chats) are kept.'
    ;;
  restart)
    require_docker; require_env
    compose restart
    wait_ready
    ;;
  backup)
    require_docker; require_env
    backup
    ;;
  restore-test)
    if [[ -z "${2:-}" ]]; then echo 'Usage: restore-test BACKUP_DIR' >&2; exit 2; fi
    require_docker; require_env
    restore_test "$2"
    ;;
  restore)
    if [[ -z "${2:-}" ]]; then echo 'Usage: restore BACKUP_DIR [--replace]' >&2; exit 2; fi
    require_docker
    restore "$2" "${3:-}"
    ;;
  help|-h|--help) help ;;
  *) echo "Unknown command: $1" >&2; help; exit 2 ;;
esac
