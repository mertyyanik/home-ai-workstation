#!/usr/bin/env bash
# Fixture tests for scripts/aiws.sh. Uses a fake docker CLI, so it needs no GPU and
# touches no real service. Secrets generated here are throwaway temporary values.
#
#   bash scripts/test-aiws.sh
set -uo pipefail
SRC="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
pass=0; fail=0
ok()  { echo "PASS: $1"; pass=$((pass+1)); }
bad() { echo "FAIL: $1"; fail=$((fail+1)); }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

T="$(mktemp -d)"; trap 'rm -rf -- "$T"; [[ -n "${SRV:-}" ]] && kill "$SRV" 2>/dev/null' EXIT
mkdir -p "$T/bin"
cat > "$T/bin/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  *"ps -q --status running"*) [[ "${FAKE_RUNNING:-1}" == 1 ]] && echo cid ;;
  *"ps -q"*) echo cid ;;
  inspect*) echo "${FAKE_HEALTH:-healthy}" ;;
  *"df -Pk"*) printf 'Filesystem 1024-blocks Used Available Capacity Mounted\n/dev/x 100 1 %s 1%% /\n' "${FAKE_FREE_KB:-104857600}" ;;
  *"config --images"*) echo 'ollama/ollama:test'; echo 'ghcr.io/open-webui/open-webui:test' ;;
  *"--entrypoint tar open-webui -C"*)
    [[ "${FAKE_TAR_FAIL:-0}" == 1 ]] && exit 1
    d="$(mktemp -d)"; echo db > "$d/webui.db"; tar -C "$d" -czf - .; rm -rf "$d" ;;
  *"--entrypoint tar open-webui -xzf"*) cat > "$FAKE_RESTORED" ;;
  *"--entrypoint sh open-webui"*"echo present"*) echo "${FAKE_DB:-absent}" ;;
  *"--entrypoint sh open-webui"*"-delete"*) echo cleared >> "$FAKE_DOCKER_LOG" ;;
  *"--entrypoint tar"*"-xzf"*) cat > /dev/null ;;
  *"--entrypoint python3"*) echo 'integrity=ok'; echo 'users=1'; echo 'chats=1' ;;
esac
exit 0
EOF
chmod +x "$T/bin/docker"
export PATH="$T/bin:$PATH" FAKE_DOCKER_LOG="$T/docker.log" FAKE_RESTORED="$T/restored.tgz"
unset XDG_CONFIG_HOME AIWS_ENV_FILE

new_repo() {
  mkdir -p "$1/scripts"
  cp "$SRC/scripts/aiws.sh" "$1/scripts/"
  cp "$SRC/.env.example" "$SRC/compose.yaml" "$1/"
}
HEX='^WEBUI_SECRET_KEY=[a-f0-9]{64}$'

# 1. Default location outside the repository
R="$T/repo1"; new_repo "$R"; export HOME="$T/home1"; mkdir -p "$HOME/.config"; chmod 755 "$HOME/.config"
A="$R/scripts/aiws.sh"
E="$HOME/.config/home-ai-workstation/aiws.env"
out="$(bash "$A" init 2>&1)"
check "init creates default env file" '[[ -f "$E" ]]'
check "no env file in repo" '[[ ! -e "$R/.env" ]]'
check "env file mode 600" '[[ "$(stat -c %a "$E")" == 600 ]]'
check "config dir mode 700" '[[ "$(stat -c %a "$(dirname "$E")")" == 700 ]]'
check "secret is 64 hex" 'grep -Eq "$HEX" "$E"'
check "no CR in env file" '! grep -q $'"'"'\r'"'"' "$E"'
check "no temp files left" '[[ -z "$(ls -A "$(dirname "$E")" | grep -v "^aiws.env$")" ]]'
check "no warnings for WSL path" '! grep -q WARNING <<<"$out"'
check "pinned tags copied from template" 'grep -q "^OLLAMA_TAG=0.40.14@sha256:" "$E"'
sum1="$(sha256sum "$E")"
out="$(bash "$A" init 2>&1)"
check "second init refuses" 'grep -q "Already initialized" <<<"$out"'
check "secret unchanged" '[[ "$(sha256sum "$E")" == "$sum1" ]]'

# 2. Commands use the env file; empty DEFAULT_MODEL falls back
sed -i 's/^DEFAULT_MODEL=.*/DEFAULT_MODEL=/' "$E"
: > "$FAKE_DOCKER_LOG"
bash "$A" pull >/dev/null 2>&1
check "pull passes --env-file and default model" 'grep -q -- "--env-file $E exec -T ollama ollama pull qwen3:4b" "$FAKE_DOCKER_LOG"'

# 3. up waits for readiness, within a limit
sed -i 's/^OPEN_WEBUI_PORT=.*/OPEN_WEBUI_PORT=3199/' "$E"
out="$(bash "$A" up 2>&1)"; rc=$?
check "up succeeds when healthy" '[[ $rc -eq 0 ]]'
check "up reports ready" 'grep -q "are ready" <<<"$out"'
check "up prints configured port" 'grep -q "localhost:3199" <<<"$out"'
out="$(FAKE_HEALTH=starting AIWS_READY_TIMEOUT=3 bash "$A" up 2>&1)"; rc=$?
check "up fails on readiness timeout" '[[ $rc -ne 0 ]]'
check "timeout message is clear" 'grep -q "not ready within 3s" <<<"$out"'
: > "$FAKE_DOCKER_LOG"
FAKE_HEALTH=starting AIWS_READY_TIMEOUT=3 bash "$A" up >/dev/null 2>&1
check "timeout shows bounded logs" 'grep -q -- "logs --tail=30" "$FAKE_DOCKER_LOG"'
out="$(FAKE_HEALTH=starting AIWS_READY_TIMEOUT=3 bash "$A" restart 2>&1)"; rc=$?
check "restart also checks readiness" '[[ $rc -ne 0 ]]'

# 4. down keeps volumes
: > "$FAKE_DOCKER_LOG"
out="$(bash "$A" down 2>&1)"; rc=$?
check "down succeeds" '[[ $rc -eq 0 ]]'
check "down runs compose down" 'grep -Eq -- "--env-file .* down$" "$FAKE_DOCKER_LOG"'
check "down never passes -v" '! grep -Eq -- "down.*(-v|--volumes)" "$FAKE_DOCKER_LOG"'
: > "$FAKE_DOCKER_LOG"
bash "$A" down -v >/dev/null 2>&1
check "down ignores a -v argument" '! grep -Eq -- "down.*(-v|--volumes)" "$FAKE_DOCKER_LOG"'

# 5. logs are bounded by default
: > "$FAKE_DOCKER_LOG"
bash "$A" logs >/dev/null 2>&1
check "logs default has no follow" 'grep -q -- "logs --tail=100$" "$FAKE_DOCKER_LOG"'
: > "$FAKE_DOCKER_LOG"
bash "$A" logs ollama >/dev/null 2>&1
check "logs accepts a service" 'grep -q -- "logs --tail=100 ollama$" "$FAKE_DOCKER_LOG"'
: > "$FAKE_DOCKER_LOG"
bash "$A" logs -f ollama >/dev/null 2>&1
check "logs -f follows" 'grep -q -- "logs --tail=100 -f ollama$" "$FAKE_DOCKER_LOG"'

# 6. status adapts to running state
: > "$FAKE_DOCKER_LOG"
out="$(bash "$A" status 2>&1)"; rc=$?
check "status running succeeds" '[[ $rc -eq 0 ]]'
check "status shows models and GPU" 'grep -q "ollama ollama ps" "$FAKE_DOCKER_LOG" && grep -q "nvidia-smi" "$FAKE_DOCKER_LOG"'
check "status shows URL" 'grep -q "localhost:3199" <<<"$out"'
out="$(FAKE_RUNNING=0 bash "$A" status 2>&1)"; rc=$?
check "status stopped still succeeds" '[[ $rc -eq 0 ]]'
check "status stopped says so" 'grep -q "Ollama is not running" <<<"$out"'

# 7. doctor: disk, port, no secret
out="$(bash "$A" doctor 2>&1)"; rc=$?
check "doctor succeeds" '[[ $rc -eq 0 ]]'
check "doctor reports env path" 'grep -q "Env file: $E" <<<"$out"'
check "doctor reports disk" 'grep -q "Disk free (WSL home)" <<<"$out" && grep -q "Disk free (Ollama models): 100 GiB" <<<"$out"'
check "doctor reports free port" 'grep -q "port 3199 is free" <<<"$out"'
check "doctor does not print secret" '! grep -q "$(sed -n "s/^WEBUI_SECRET_KEY=//p" "$E")" <<<"$out"'
out="$(FAKE_FREE_KB=1048576 bash "$A" doctor 2>&1)"; rc=$?
check "low disk warns without failing" '[[ $rc -eq 0 ]] && grep -q "less than 20 GiB free for Ollama models" <<<"$out"'
python3 -m http.server 3198 --bind 127.0.0.1 >/dev/null 2>&1 & SRV=$!
for i in 1 2 3 4 5 6 7 8 9 10; do (: </dev/tcp/127.0.0.1/3198) 2>/dev/null && break; sleep 0.3; done
sed -i 's/^OPEN_WEBUI_PORT=.*/OPEN_WEBUI_PORT=3198/' "$E"
out="$(FAKE_RUNNING=0 bash "$A" doctor 2>&1)"; rc=$?
check "port conflict warns without failing" '[[ $rc -eq 0 ]] && grep -q "port 3198 is already in use" <<<"$out"'
out="$(FAKE_RUNNING=1 bash "$A" doctor 2>&1)"
check "port served by WebUI is OK" 'grep -q "port 3198 is served by Open WebUI" <<<"$out"'
kill "$SRV" 2>/dev/null; SRV=
chmod 644 "$E"
out="$(bash "$A" doctor 2>&1)"
check "doctor warns on loose permissions" 'grep -q "permissions are 644" <<<"$out"'

# 8. Invalid secret is rejected
sed -i 's/^WEBUI_SECRET_KEY=.*/WEBUI_SECRET_KEY=short/' "$E"
bash "$A" status >/dev/null 2>&1; rc=$?
check "invalid secret rejected" '[[ $rc -ne 0 ]]'

# 9. Legacy repository .env still wins when present
R="$T/repo2"; new_repo "$R"; export HOME="$T/home2"; mkdir -p "$HOME"
printf 'WEBUI_SECRET_KEY=%s\n' "$(printf '0%.0s' {1..64})" > "$R/.env"
: > "$FAKE_DOCKER_LOG"
bash "$R/scripts/aiws.sh" status >/dev/null 2>&1
check "legacy .env used" 'grep -q -- "--env-file .env ps" "$FAKE_DOCKER_LOG"'
out="$(bash "$R/scripts/aiws.sh" init 2>&1)"
check "init keeps legacy .env" 'grep -q "Already initialized (.env exists)" <<<"$out"'
check "no default file created" '[[ ! -e "$HOME/.config/home-ai-workstation/aiws.env" ]]'

# 10. AIWS_ENV_FILE override wins; CRLF template handled
sed -i 's/$/\r/' "$R/.env.example"
export AIWS_ENV_FILE="$T/custom/dir/my.env"
bash "$R/scripts/aiws.sh" init >/dev/null 2>&1
check "override path created" '[[ -f "$AIWS_ENV_FILE" ]]'
check "override secret valid despite CRLF template" 'grep -Eq "$HEX" "$AIWS_ENV_FILE"'
check "override no CR" '! grep -q $'"'"'\r'"'"' "$AIWS_ENV_FILE"'
unset AIWS_ENV_FILE

# 11. In-repository override gets a note
R="$T/repo3"; new_repo "$R"; export HOME="$T/home3"; mkdir -p "$HOME"
out="$(AIWS_ENV_FILE=local.env bash "$R/scripts/aiws.sh" init 2>&1)"
check "in-repo override note" 'grep -q "inside the project folder" <<<"$out"'

# 12. backup, restore-test and restore
R="$T/repo4"; new_repo "$R"; export HOME="$T/home4"; mkdir -p "$HOME"
A="$R/scripts/aiws.sh"; E="$HOME/.config/home-ai-workstation/aiws.env"
bash "$A" init >/dev/null 2>&1
B="$HOME/.local/share/home-ai-workstation/backups"
: > "$FAKE_DOCKER_LOG"
out="$(bash "$A" backup 2>&1)"; rc=$?
D="$(sed -n 's/^Backup created: //p' <<<"$out")"
check "backup succeeds" '[[ $rc -eq 0 && -d "$D" ]]'
check "backup root mode 700" '[[ "$(stat -c %a "$B")" == 700 ]]'
check "backup env mode 600" '[[ "$(stat -c %a "$D/aiws.env")" == 600 ]]'
check "backup has all files" '[[ -f "$D/open-webui-data.tar.gz" && -f "$D/models.txt" && -f "$D/manifest.txt" && -f "$D/SHA256SUMS" ]]'
check "backup leaves no partial folder" '[[ -z "$(ls -A "$B" | grep incomplete)" ]]'
check "backup stops then starts webui" 'grep -q "stop open-webui" "$FAKE_DOCKER_LOG" && grep -q "start open-webui" "$FAKE_DOCKER_LOG"'
check "backup excludes model caches" 'grep -q -- "--exclude=./cache/embedding --exclude=./cache/whisper" "$FAKE_DOCKER_LOG"'
check "backup output hides secret" '! grep -q "$(sed -n "s/^WEBUI_SECRET_KEY=//p" "$E")" <<<"$out"'
check "manifest hides secret" '! grep -q "$(sed -n "s/^WEBUI_SECRET_KEY=//p" "$E")" "$D/manifest.txt"'
n="$(ls -A "$B" | wc -l)"; sleep 1
: > "$FAKE_DOCKER_LOG"
FAKE_TAR_FAIL=1 bash "$A" backup >/dev/null 2>&1; rc=$?
check "failed backup returns error" '[[ $rc -ne 0 ]]'
check "failed backup leaves nothing" '[[ "$(ls -A "$B" | wc -l)" == "$n" ]]'
check "failed backup restarts webui" 'grep -q "start open-webui" "$FAKE_DOCKER_LOG"'
out="$(bash "$A" restore-test "$D" 2>&1)"; rc=$?
check "restore-test succeeds" '[[ $rc -eq 0 ]] && grep -q "integrity=ok" <<<"$out"'
: > "$FAKE_DOCKER_LOG"
bash "$A" restore-test "$D" >/dev/null 2>&1
check "restore-test removes temp volume" 'grep -q "volume rm -f aiws-restore-test-" "$FAKE_DOCKER_LOG"'
check "restore-test leaves live data alone" '! grep -q "cleared" "$FAKE_DOCKER_LOG"'
BAD="$T/bad"; cp -r "$D" "$BAD"; echo x >> "$BAD/open-webui-data.tar.gz"
bash "$A" restore-test "$BAD" >/dev/null 2>&1; rc=$?
check "damaged backup rejected" '[[ $rc -ne 0 ]]'
: > "$FAKE_DOCKER_LOG"
FAKE_DB=present bash "$A" restore "$BAD" --replace >/dev/null 2>&1; rc=$?
check "replace refuses damaged backup" '[[ $rc -ne 0 ]] && ! grep -q "cleared" "$FAKE_DOCKER_LOG"'
: > "$FAKE_DOCKER_LOG"
out="$(FAKE_DB=present bash "$A" restore "$D" 2>&1)"; rc=$?
check "restore refuses existing data" '[[ $rc -ne 0 ]] && grep -q "already has data" <<<"$out"'
check "refused restore changes nothing" '! grep -q "cleared" "$FAKE_DOCKER_LOG"'
: > "$FAKE_DOCKER_LOG"
out="$(FAKE_DB=unknown bash "$A" restore "$D" --replace 2>&1)"; rc=$?
check "unknown volume state stops restore" '[[ $rc -ne 0 ]] && ! grep -q "cleared" "$FAKE_DOCKER_LOG"'
out="$(bash "$A" restore "$D" --force 2>&1)"; rc=$?
check "unknown restore option rejected" '[[ $rc -eq 2 ]]'
n="$(ls -A "$B" | wc -l)"; sleep 1
: > "$FAKE_DOCKER_LOG"
out="$(FAKE_DB=present bash "$A" restore "$D" --replace 2>&1)"; rc=$?
check "replace succeeds" '[[ $rc -eq 0 ]]'
check "replace takes safety backup" '[[ "$(ls -A "$B" | wc -l)" -gt "$n" ]] && grep -q "safety backup" <<<"$out"'
check "replace extracts same archive" 'cmp -s "$FAKE_RESTORED" "$D/open-webui-data.tar.gz"'
: > "$FAKE_DOCKER_LOG"
out="$(bash "$A" restore "$D" 2>&1)"; rc=$?
check "restore into empty volume succeeds" '[[ $rc -eq 0 ]]'
sum1="$(sha256sum "$E")"
sed -i 's/^WEBUI_SECRET_KEY=.*/WEBUI_SECRET_KEY=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/' "$E"
sum2="$(sha256sum "$E")"
out="$(bash "$A" restore "$D" 2>&1)"
check "different secret warns" 'grep -q "secret differs" <<<"$out"'
check "existing env file not replaced" '[[ "$(sha256sum "$E")" == "$sum2" ]]'
rm -f "$E"
out="$(bash "$A" restore "$D" 2>&1)"; rc=$?
check "new machine restores env file" '[[ $rc -eq 0 && -f "$E" && "$(stat -c %a "$E")" == 600 ]]'
check "restored env equals original" '[[ "$(sha256sum "$E")" == "$sum1" ]]'
bash "$A" restore >/dev/null 2>&1; rc=$?
check "restore needs a folder" '[[ $rc -eq 2 ]]'

# 13. chat and ML switch
: > "$FAKE_DOCKER_LOG"
out="$(bash "$A" ml 2>&1)"; rc=$?
check "ml stops only ollama" '[[ $rc -eq 0 ]] && grep -q "stop ollama$" "$FAKE_DOCKER_LOG" && ! grep -q "stop open-webui" "$FAKE_DOCKER_LOG"'
check "ml explains how to return" 'grep -q "aiws.sh chat" <<<"$out"'
: > "$FAKE_DOCKER_LOG"
out="$(bash "$A" chat 2>&1)"; rc=$?
check "chat starts and waits" '[[ $rc -eq 0 ]] && grep -q "up -d" "$FAKE_DOCKER_LOG" && grep -q "are ready" <<<"$out"'

echo "---- $pass passed, $fail failed"
[[ $fail -eq 0 ]]
