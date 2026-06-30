#!/bin/bash
# Deterministic verification for payments-incident, read back through the Sentry API
# (never trusting agent narration). Uses Python stdlib only (no curl dependency), to
# match the clone's stdlib-only ethos and run on the thin agent base.
#
# reward=1 iff BOTH:
#   (A) PAYMENTS-501 is resolved AND resolved in release payments-api@2026.06.07.2, and
#   (B) PAYMENTS-501 carries a NEW non-empty comment (the fixture seeds zero comments,
#       so any comment present is agent-authored).
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true

reward="$(python3 - <<'PY'
import json, os, sys, urllib.request

api = os.environ.get("SENTRY_URL", "http://sentry").rstrip("/")
token = os.environ.get("SENTRY_AUTH_TOKEN", "test-token-acme-eval")

def get(path):
    req = urllib.request.Request(api + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

try:
    issue = get("/api/0/issues/PAYMENTS-501/")
    comments = get("/api/0/issues/PAYMENTS-501/comments/")
except Exception as exc:
    sys.stderr.write(f"[verifier] api error: {exc}\n")
    print("0"); raise SystemExit

status_ok = issue.get("status") == "resolved" and \
    issue.get("resolvedInRelease") == "payments-api@2026.06.07.2"
comment_ok = any(
    isinstance(c, dict) and str(c.get("text", "")).strip()
    for c in (comments if isinstance(comments, list) else [])
)
sys.stderr.write(f"[verifier] status_ok={status_ok} comment_ok={comment_ok}\n")
print("1" if (status_ok and comment_ok) else "0")
PY
)"

echo "${reward:-0}" > /logs/verifier/reward.txt
echo "reward=${reward:-0}"
exit 0
