#!/usr/bin/env bash
set -uo pipefail
R=acme/svc

# ---- auth + api ----
gh auth status >/dev/null
gh auth token >/dev/null
gh api user >/dev/null

# ---- repo: view/list/edit/clone ----
gh repo view $R >/dev/null
gh api "repos/$R" >/dev/null
gh repo list >/dev/null
gh repo edit $R -d "coverage-edited"
cd /tmp && rm -rf svc && gh repo clone $R svc && cd svc

# ---- labels ----
gh label create -R $R -n audit -c ededed -d "audit label" || true
gh label list -R $R >/dev/null

# ---- issues: create/view/list/comment/edit/close/reopen ----
IU=$(gh issue create -R $R -t "Coverage incident" -b "incident body")
IN=$(echo "$IU" | grep -oE '[0-9]+$')
gh issue view $IN -R $R >/dev/null
gh api "repos/$R/issues/$IN" >/dev/null
gh issue list -R $R >/dev/null
gh issue comment $IN -R $R -b "investigating"
gh issue edit $IN -R $R --add-label audit
gh issue close $IN -R $R
gh issue reopen $IN -R $R
gh issue close $IN -R $R

# ---- milestone (hidden but functional) ----
gh milestone create -R $R -t M1 -d "sprint 1" || true
gh milestone list -R $R >/dev/null

# ---- pull request: create/view/list/diff/review/merge ----
git checkout -b add-subtract >/dev/null 2>&1
printf 'def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n' > app.py
git add -A && git commit -q -m "add subtract"
git push -q origin add-subtract
PU=$(gh pr create -R $R -t "Add subtract" -H add-subtract -B main -b "adds subtract")
PN=$(echo "$PU" | grep -oE '[0-9]+$')
gh pr view $PN -R $R >/dev/null
gh pr list -R $R >/dev/null
gh pr diff $PN -R $R >/dev/null
gh pr review $PN -R $R --approve -b "lgtm"
for i in $(seq 1 10); do gh pr merge $PN -R $R --method squash && break || sleep 2; done

# ---- release ----
gh release create v9.9 -R $R -t "v9.9" -n "release notes"
gh release list -R $R >/dev/null

# ---- actions: workflow + run + artifact ----
WF=$(gh workflow list -R $R | grep -oE '[^ ]+\.ya?ml' | head -1)
gh workflow run "$WF" -R $R --ref main
for i in $(seq 1 60); do
  st=$(gh api repos/$R/actions/tasks 2>/dev/null | python3 -c 'import sys,json;ws=json.load(sys.stdin).get("workflow_runs",[]);print(ws[0]["status"] if ws else "none")' 2>/dev/null || echo none)
  [ "$st" = success ] && break
  [ "$st" = failure ] && break
  sleep 5
done
gh run list -R $R >/dev/null
RN=$(gh api "repos/$R/actions/tasks" 2>/dev/null | python3 -c 'import sys,json;xs=json.load(sys.stdin).get("workflow_runs",[]);print((xs[0].get("run_number") or xs[0].get("id")) if xs else 1)' 2>/dev/null || echo 1)
gh run view "$RN" -R $R >/dev/null 2>&1 || true
rm -rf /tmp/art && mkdir -p /tmp/art
gh run download -R $R -D /tmp/art 2>/dev/null || true
CODE=$(cat /tmp/art/*/code.txt 2>/dev/null | tr -d '[:space:]')
[ -n "$CODE" ] && gh issue create -R $R -t "$CODE" -b "build code from artifact"
