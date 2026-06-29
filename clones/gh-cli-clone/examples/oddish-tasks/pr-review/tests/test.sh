#!/usr/bin/env bash
# Pass iff PR #1 ends OPEN and its timeline shows it was closed then reopened
# (i.e. the agent reviewed -> closed -> reopened). checkout + diff are read-only
# and confirmed via the trajectory.
set -uo pipefail; mkdir -p /logs/verifier
R=acme/lib
py(){ python3 -c "$1" 2>/dev/null || echo 0; }
state=$(gh api "repos/$R/pulls/1" 2>/dev/null | py 'import sys,json;print(json.load(sys.stdin).get("state",""))')
tl=$(gh api repos/$R/issues/1/timeline 2>/dev/null)
closed=$(echo "$tl" | py 'import sys,json;print(int(any(e.get("type") in ("close","closed") for e in json.load(sys.stdin))))')
reopened=$(echo "$tl" | py 'import sys,json;print(int(any(e.get("type") in ("reopen","reopened") for e in json.load(sys.stdin))))')
ok=0; [ "$state" = open ] && [ "${closed:-0}" = 1 ] && [ "${reopened:-0}" = 1 ] && ok=1
echo $ok >/logs/verifier/reward.txt
echo "state=$state closed_event=$closed reopened_event=$reopened -> $ok"
