#!/usr/bin/env bash
# Verifier for stale-pr-sweep.
# Reward 1 iff: feat/auth-refresh PR still open, feat/dark-mode and
# feat/export-csv PRs are closed and each has at least one comment.
set -uo pipefail
mkdir -p /logs/verifier

R=acme/platform
py() { python3 -c "$1" 2>/dev/null || echo ''; }

# Fetch all PRs (open + closed)
PRS=$(gh api "repos/$R/pulls?state=all&limit=50" 2>/dev/null)

auth_state=$(echo "$PRS" | py \
  'import sys,json; xs=json.load(sys.stdin); r=[p["state"] for p in xs if p["head"]["ref"]=="feat/auth-refresh"]; print(r[0] if r else "missing")')

dark_state=$(echo "$PRS" | py \
  'import sys,json; xs=json.load(sys.stdin); r=[p["state"] for p in xs if p["head"]["ref"]=="feat/dark-mode"]; print(r[0] if r else "missing")')
dark_num=$(echo "$PRS" | py \
  'import sys,json; xs=json.load(sys.stdin); r=[str(p["number"]) for p in xs if p["head"]["ref"]=="feat/dark-mode"]; print(r[0] if r else "0")')

csv_state=$(echo "$PRS" | py \
  'import sys,json; xs=json.load(sys.stdin); r=[p["state"] for p in xs if p["head"]["ref"]=="feat/export-csv"]; print(r[0] if r else "missing")')
csv_num=$(echo "$PRS" | py \
  'import sys,json; xs=json.load(sys.stdin); r=[str(p["number"]) for p in xs if p["head"]["ref"]=="feat/export-csv"]; print(r[0] if r else "0")')

dark_comments=0
csv_comments=0
[ "${dark_num:-0}" != "0" ] && dark_comments=$(gh api "repos/$R/issues/$dark_num/comments" 2>/dev/null \
  | py 'import sys,json; print(len(json.load(sys.stdin)))' || echo 0)
[ "${csv_num:-0}" != "0" ] && csv_comments=$(gh api "repos/$R/issues/$csv_num/comments" 2>/dev/null \
  | py 'import sys,json; print(len(json.load(sys.stdin)))' || echo 0)

ok=0
[ "$auth_state" = "open" ] \
  && [ "$dark_state" = "closed" ] \
  && [ "$csv_state" = "closed" ] \
  && [ "${dark_comments:-0}" -ge 1 ] \
  && [ "${csv_comments:-0}" -ge 1 ] \
  && ok=1

echo $ok > /logs/verifier/reward.txt
echo "auth_open=$auth_state dark_closed=$dark_state dark_comments=$dark_comments csv_closed=$csv_state csv_comments=$csv_comments -> $ok"
