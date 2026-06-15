#!/usr/bin/env bash
# Verifier for figma-linear-handoff (multi-tool: Figma + Linear).
#
# reward=1 iff ALL:
#   (A) the candidate pricing_card package passes the visible invariant tests AND the
#       HIDDEN grader (exact spec recovered from the Figma file), graded in a fresh
#       verifier-owned dir (NOT /app), and
#   (B) the Linear ticket DES-101 is now "In Review" or "Done", read back via the
#       `linear` CLI (never trusting narration), AND
#   (C) DES-101 has a NEW comment authored by the agent (the seed comments are by
#       rae/mira; an agent-authored comment is the agent's).
set -uo pipefail
mkdir -p /logs/verifier 2>/dev/null || true
HERE="$(cd "$(dirname "$0")" && pwd)"

# ---- (A) grade the code in an isolated dir ----
GRADE="/tmp/grade.$$"
mkdir -p "$GRADE"
cp -r /app/pricing_card "$GRADE/pricing_card"
cp "$HERE/trusted/test_states.py" "$HERE/trusted/test_grade.py" "$GRADE/"
code_ok=0
( cd "$GRADE" && python3 -m pytest -q ) > /logs/verifier/pytest.log 2>&1 && code_ok=1
echo "[verifier] code_ok=$code_ok"; tail -n 2 /logs/verifier/pytest.log 2>/dev/null || true

# ---- (B)+(C) read the ticket back through the Linear CLI ----
ticket_json="$(linear issue view DES-101 --comments --json 2>/dev/null || echo '{}')"
read state_ok comment_ok <<<"$(python3 - "$ticket_json" <<'PY'
import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("0 0"); raise SystemExit
state = (d.get("state") or {}).get("name", "")
state_ok = 1 if state in ("In Review", "Done") else 0
comment_ok = 1 if any((c.get("author") or {}).get("handle") == "agent"
                      for c in d.get("comments", [])) else 0
print(f"{state_ok} {comment_ok}")
PY
)"
echo "[verifier] state_ok=$state_ok comment_ok=$comment_ok"

reward=0
[ "$code_ok" = 1 ] && [ "$state_ok" = 1 ] && [ "$comment_ok" = 1 ] && reward=1
echo "$reward" > /logs/verifier/reward.txt 2>/dev/null || true
echo "reward=$reward"
exit 0
