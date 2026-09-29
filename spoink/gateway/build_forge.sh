#!/usr/bin/env bash
# Bake spoink GitHub snapshots into a ghc-service (Forgejo) image, time-aligned.
#   build_forge.sh <snapshots-dir> <image-tag> [as-of-ISO] [base-image]
#
# Unlike the slack/jira/logfire bakes (drop a file into a `docker build`), the
# GitHub clone's served form is a *running* Forgejo: data only goes in by
# replaying a snapshot into a live forge. So this is a boot -> hydrate -> commit:
#   1. boot ghc-service (Forgejo + ghclone, admin user `acme`, token at /shared/token)
#   2. `ghc-hydrate apply <snap> --into acme/<repo> --as-of T` for each repo
#      (owner MUST equal the forge admin login `acme`, else silent 404s)
#   3. docker commit the running forge -> <image-tag>  (publish() then pushes it)
set -euo pipefail
SNAPS="${1:?snapshots dir}"; TAG="${2:?image tag}"; AS_OF="${3:-}"
BASE="${4:-ghcr.io/abundant-ai/ghc-service:latest}"
OWNER="acme"                       # admin login the ghc-service entrypoint creates
NAME="spoink-forge-bake-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

[ -f "$SNAPS/manifest.json" ] || { echo "no manifest.json under $SNAPS" >&2; exit 1; }
# read the repo list portably (no bash-4 `mapfile`; macOS ships bash 3.2)
REPOS=()
while IFS= read -r r; do [ -n "$r" ] && REPOS+=("$r"); done < <(python3 - "$SNAPS" <<'PY'
import json, os, sys
m = json.load(open(os.path.join(sys.argv[1], "manifest.json")))
for r in m.get("repos", []):        # ["org/repo", ...] (the successfully snapshotted ones)
    print(r)
PY
)
[ "${#REPOS[@]}" -gt 0 ] || { echo "manifest.json lists no repos" >&2; exit 1; }

echo ">> booting $BASE as $NAME"
docker run -d --name "$NAME" "$BASE" >/dev/null

echo ">> waiting for forge to be ready"
for i in $(seq 1 120); do
  if docker exec "$NAME" sh -c 'test -s /shared/token && curl -fsS http://localhost/api/healthz >/dev/null 2>&1'; then
    break
  fi
  sleep 1
  if [ "$i" = 120 ]; then echo "forge never became ready" >&2; docker logs "$NAME" 2>&1 | tail -30 >&2; exit 1; fi
done

echo ">> copying ${#REPOS[@]} snapshot(s) into the forge"
docker cp "$SNAPS/." "$NAME:/snap"

ASOPT=()
[ -n "$AS_OF" ] && ASOPT=(--as-of "$AS_OF")

for full in "${REPOS[@]}"; do
  name="${full##*/}"               # repo name without owner
  dir="/snap/${full//\//__}"       # spoink writes snapshot dirs as <org>__<repo>
  echo ">> apply $full -> $OWNER/$name ${AS_OF:+(as of $AS_OF)}"
  docker exec -e GH_HOST=http://localhost "$NAME" \
    python -m ghclone.cli.admin apply "$dir" --into "$OWNER/$name" "${ASOPT[@]}"
done

echo ">> committing $NAME -> $TAG"
docker commit "$NAME" "$TAG" >/dev/null
echo "built $TAG"
