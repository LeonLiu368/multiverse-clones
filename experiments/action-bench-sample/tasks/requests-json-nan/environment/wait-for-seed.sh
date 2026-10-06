#!/usr/bin/env bash
# Block until the github sidecar's seed has pushed the buggy repo snapshot to
# main. This gates `main`'s healthcheck so neither the agent nor the verifier
# acts before the source code exists on main — eliminating the seed race that
# otherwise surfaces as a HARNESS_ERROR. The Linear (ticketvector) and Slack
# seeds are static volume mounts and are ready as soon as their services come
# up, so polling the github content is sufficient.
# Arg 1: repository name under the meridian/ org (e.g. webapp).
# Arg 2: a sentinel path that must exist on main (e.g. requests/sessions.py).
set -u
repo="${1:?repo name required}"
sentinel="${2:?sentinel path required}"
for _ in $(seq 1 150); do
  t="$(cat /run/secrets/token 2>/dev/null || true)"
  if [ -n "$t" ] && curl -sf -H "Authorization: token $t" \
      "http://github/api/v1/repos/meridian/${repo}/contents/${sentinel}?ref=main" 2>/dev/null \
      | grep -q '"sha"'; then
    touch /tmp/seed-ready
    exit 0
  fi
  sleep 2
done
echo "wait-for-seed: ${sentinel} on meridian/${repo}@main never appeared" >&2
exit 1
