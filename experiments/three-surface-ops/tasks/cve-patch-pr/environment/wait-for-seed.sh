#!/usr/bin/env bash
# Block until the github sidecar's seed has pushed the repo and opened the
# review PR. This gates `main`'s healthcheck, so neither the agent nor the
# verifier can act before the repo, fix branch, and open PR all exist —
# eliminating the seed race that otherwise surfaces as a HARNESS_ERROR.
# Arg 1: repository name under the acme/ org (e.g. webapp).
set -u
repo="${1:?repo name required}"
for _ in $(seq 1 150); do
  t="$(cat /run/secrets/token 2>/dev/null || true)"
  if [ -n "$t" ] && curl -sf -H "Authorization: token $t" \
      "http://github/api/v1/repos/acme/${repo}/pulls?state=open" 2>/dev/null \
      | grep -q '"number"'; then
    touch /tmp/seed-ready
    exit 0
  fi
  sleep 2
done
echo "wait-for-seed: open PR for acme/${repo} never appeared" >&2
exit 1
