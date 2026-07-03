#!/usr/bin/env bash
# provision-gitsync.sh — idempotent Dokku provisioning for a live task, driven
# entirely through `docker exec` against the dokku container (the operator
# surface). No host ports needed: the deploy uses `dokku git:sync --build`
# from a path INSIDE the dokku container, so provisioning never touches SSH
# (SSH is reserved as the AGENT surface).
#
# (Named -gitsync to coexist with the concurrently-authored provision.sh,
#  which deploys via host-side `git push` over a published SSH port.)
#
# Steps (spike-proven recipe, ../README.md):
#   1. wait for `dokku version`
#   2. dokku events:on                      (verifier audit trail)
#   3. dokku ssh-keys:add agent <mounted pubkey>
#   4. dokku apps:create <app>
#   5. dokku config:set --no-restart <app> <FAULTY env>
#   6. dokku network:set <app> attach-post-create <task network>
#      (network auto-discovered from the dokku container's own networks)
#   7. deploy: copy mounted repo source -> rw tmpdir, git init+commit,
#      dokku git:sync --build <app> <tmpdir>
#   8. wait until <app>.web.1:<port> answers <health-path> on the task network
#
# Usage:
#   provision-gitsync.sh \
#     --dokku-container <name>     docker name of the dokku service (default: dokku)
#     --app conduit                app name (default: conduit)
#     --pubkey /mnt/keys/agent_key.pub   pre-generated agent PUBLIC key, path
#                                        INSIDE the dokku container (default shown)
#     --sut /mnt/sut               SUT repo source, path INSIDE the dokku
#                                  container (default shown)
#     --config "K=V K=V ..."       FAULTY runtime env to arm (required)
#     --port 8000                  app port (default 8000)
#     --health-path /api/tags      readiness path (default /api/tags)
#     --net <network>              task network (default: auto-discover)
#     --timeout 300                deploy+health wait budget, seconds
set -euo pipefail

DOKKU=dokku
APP=conduit
PUBKEY=/mnt/keys/agent_key.pub
SUT=/mnt/sut
CONFIG=""
PORT=8000
HEALTH=/api/tags
NET=""
TIMEOUT=300

while [ $# -gt 0 ]; do
  case "$1" in
    --dokku-container) DOKKU="$2"; shift 2;;
    --app) APP="$2"; shift 2;;
    --pubkey) PUBKEY="$2"; shift 2;;
    --sut) SUT="$2"; shift 2;;
    --config) CONFIG="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --health-path) HEALTH="$2"; shift 2;;
    --net) NET="$2"; shift 2;;
    --timeout) TIMEOUT="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$CONFIG" ] || { echo "ERROR: --config (faulty env) required" >&2; exit 2; }

dexec() { docker exec "$DOKKU" "$@"; }
say() { echo "[provision $(date +%H:%M:%S)] $*"; }
t0=$SECONDS

# 1. wait for dokku
say "waiting for dokku to answer..."
until dexec dokku version >/dev/null 2>&1; do sleep 2; done
say "dokku up ($((SECONDS-t0))s)"

# 2. events audit trail
dexec dokku events:on >/dev/null
say "events:on"

# 3. agent key (idempotent: remove-then-add)
dexec dokku ssh-keys:remove agent >/dev/null 2>&1 || true
dexec sh -c "dokku ssh-keys:add agent '$PUBKEY'" >/dev/null
say "agent ssh key authorized"

# 4. app
if ! dexec dokku apps:exists "$APP" >/dev/null 2>&1; then
  dexec dokku apps:create "$APP" >/dev/null
  say "app created: $APP"
else
  say "app exists: $APP"
fi

# 5. faulty env (no restart yet — nothing deployed)
# shellcheck disable=SC2086
dexec dokku config:set --no-restart "$APP" $CONFIG >/dev/null
say "faulty config armed: $CONFIG"

# 6. task network (discover from the dokku container itself if not given)
if [ -z "$NET" ]; then
  NET=$(docker inspect "$DOKKU" \
    --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
    | tr ' ' '\n' | grep -v '^bridge$' | grep -v '^$' | head -1)
fi
[ -n "$NET" ] || { echo "ERROR: could not discover task network" >&2; exit 1; }
dexec dokku network:set "$APP" attach-post-create "$NET"
say "network:set $APP attach-post-create $NET"

# 7. deploy via git:sync from a local (in-container) path.
#    VERIFIED: `dokku git:sync --build <app> <local path>` clones a plain local
#    git repo over git's file transport — no SSH involved.
tdeploy=$SECONDS
dexec sh -c "
  set -e
  rm -rf /tmp/sut-repo && cp -R '$SUT' /tmp/sut-repo && cd /tmp/sut-repo
  git init -q -b master   # dokku's default deploy-branch is 'master'
  git config user.email provision@local && git config user.name provision
  git add -A && git commit -qm 'sut deploy' --no-verify
  chown -R dokku:dokku /tmp/sut-repo   # git:sync clones as the dokku user
" >/dev/null
say "deploy repo assembled in-container; running git:sync --build..."
dexec dokku git:sync --build "$APP" /tmp/sut-repo
say "git:sync deploy done ($((SECONDS-tdeploy))s)"

# 8. health: direct container-name path, from inside the task network.
#    The dokku container itself is attached to $NET, so exec a check from it.
say "waiting for $APP.web.1:$PORT$HEALTH ..."
thealth=$SECONDS
until dexec curl -fsS -m 3 "http://$APP.web.1:$PORT$HEALTH" >/dev/null 2>&1; do
  [ $((SECONDS-thealth)) -lt "$TIMEOUT" ] || { echo "ERROR: app never became healthy" >&2; exit 1; }
  sleep 2
done
say "app healthy on direct container name ($((SECONDS-thealth))s wait)"
say "TOTAL provision time: $((SECONDS-t0))s"
