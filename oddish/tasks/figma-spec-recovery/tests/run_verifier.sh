#!/bin/bash
# Deterministic verification for figma-spec-recovery.
#
# reward=1 iff BOTH:
#   (A) the candidate pricing_card package passes the visible invariant tests AND
#       the HIDDEN grader (exact finalized spec recovered from the Figma file), and
#   (B) the agent posted a NEW comment on the PricingCard node (1:2) in the Figma
#       file — read back through the public API, never trusting narration.
#
# Grading runs in a fresh verifier-owned dir (NOT /workspace) so the agent can't
# pre-place a passing tests/ tree. "NEW" comment = millisecond-epoch id (>1e12);
# seeded comments have small ids (1..5).
set -uo pipefail
mkdir -p /logs/verifier
HERE="$(cd "$(dirname "$0")" && pwd)"
API="${FIGMA_API_URL:-http://figma:3000}"
TOKEN="${FIGMA_TOKEN:-figma-clone-token}"
KEY="${FIGMA_FILE_KEY:-Pr1cingCardSpecFile001}"

# ---- (A) grade the code in an isolated dir ----
GRADE="/tmp/grade.$$"
mkdir -p "$GRADE"
cp -r /workspace/pricing_card "$GRADE/pricing_card"
cp "$HERE/trusted/test_card.py" "$HERE/trusted/test_grade_card.py" "$GRADE/"
code_ok=0
( cd "$GRADE" && python3 -m pytest -q ) > /logs/verifier/pytest.log 2>&1 && code_ok=1
echo "[verifier] code_ok=$code_ok" ; tail -n 3 /logs/verifier/pytest.log

# ---- (B) comms check: a NEW comment on node 1:2, read back via the API ----
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
    if cid.isdigit() and int(cid) > 1_000_000_000_000 and node == "1:2":
        ok = True
        break
print(1 if ok else 0)
PY
)"
echo "[verifier] comms_ok=$comms_ok"

reward=0
if [ "$code_ok" = "1" ] && [ "$comms_ok" = "1" ]; then
  reward=1
fi
echo "$reward" > /logs/verifier/reward.txt
echo "reward=$reward"
exit 0
