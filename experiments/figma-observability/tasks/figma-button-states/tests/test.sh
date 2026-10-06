#!/usr/bin/env bash
# Verifier for figma-button-states.
#
# reward=1 iff BOTH:
#   (A) the candidate button_states package passes the visible invariant tests AND
#       the HIDDEN grader (exact finalized spec recovered from node tree + comments
#       + the Primary/600 style-token resolution), graded in a fresh verifier-owned
#       dir (NOT /app, so the agent can't pre-place a passing tests tree), and
#   (B) the agent posted a NEW comment on the Button component-set node (2:0),
#       read back through the public API — never trusting narration.
#
# "NEW" comment = millisecond-epoch id (>1e12); seeded comments have small ids (1..7).
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true
HERE="$(cd "$(dirname "$0")" && pwd)"
API="${FIGMA_API_URL:-http://figma:3000}"
TOKEN="${FIGMA_TOKEN:-figma-clone-token}"
KEY="${FIGMA_FILE_KEY:-BtnStatesSpecFile0001x}"

# ---- (A) grade the code in an isolated dir ----
GRADE="/tmp/grade.$$"
mkdir -p "$GRADE"
cp -r /app/button_states "$GRADE/button_states"
cp "$HERE/trusted/test_states.py" "$HERE/trusted/test_grade_states.py" "$GRADE/"
code_ok=0
( cd "$GRADE" && python3 -m pytest -q ) > /logs/verifier/pytest.log 2>&1 && code_ok=1
echo "[verifier] code_ok=$code_ok"; tail -n 3 /logs/verifier/pytest.log 2>/dev/null || true

# ---- (B) comms check: a NEW comment on the Button node (2:0), read back via API ----
comments_json="$(curl -sf -H "X-Figma-Token: $TOKEN" "$API/v1/files/$KEY/comments" || echo '{}')"
comms_ok="$(python3 - "$comments_json" <<'PY'
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    print(0); raise SystemExit
ok = False
for c in data.get("comments", []):
    cid = str(c.get("id", ""))
    node = (c.get("client_meta") or {}).get("node_id", "")
    if cid.isdigit() and int(cid) > 1_000_000_000_000 and node == "2:0":
        ok = True
        break
print(1 if ok else 0)
PY
)"
echo "[verifier] comms_ok=$comms_ok"

reward=0
[ "$code_ok" = 1 ] && [ "$comms_ok" = 1 ] && reward=1
echo "$reward" > /logs/verifier/reward.txt 2>/dev/null || true
echo "code_ok=$code_ok comms_ok=$comms_ok -> $reward"
exit 0
