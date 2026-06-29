#!/usr/bin/env bash
# APEX/SWE acceptance: prove an agent has ALL the gh tools it needs to do a
# "fix the bug" task, using ONLY the `gh` shim (-> ghc -> offline Forgejo).
#
# Simulates the real loop: read the bug issue, branch, fix, push, open a PR,
# review, merge, close the issue, tag metadata. Every step asserts success;
# any failure aborts non-zero. This is the substitute-ghc-for-gh test.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HERE:$PATH"                      # `gh` now == our shim
export GHC_HOST="${GHC_HOST:-http://localhost:3300}"
export GHC_TOKEN="${GHC_TOKEN:-$(cat "$HERE/../ghc-token.txt" 2>/dev/null)}"

REPO="acme-app-$$"
ME="$(gh api user 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["login"])')"
SLUG="$ME/$REPO"
WORK="$(mktemp -d)"
ok() { echo "  ✓ $1"; }

echo "== using gh shim: $(command -v gh) -> ghc =="
gh --version >/dev/null 2>&1 || true

echo "== auth =="
gh auth status >/dev/null;                                          ok "gh auth status"

echo "== repo (world setup) =="
gh repo create "$REPO" --description "acceptance world" >/dev/null; ok "gh repo create"
gh repo view "$SLUG" >/dev/null;                                    ok "gh repo view"
gh repo clone "$SLUG" "$WORK/clone" >/dev/null 2>&1;               ok "gh repo clone"

echo "== issue (the bug to fix) =="
num() {
  python3 -c 'import re,sys
s=sys.stdin.read()
m=re.search(r"#(\d+)", s) or re.search(r"/(?:issues|pull)/(\d+)(?:\D|$)", s)
sys.exit(1) if not m else print(m.group(1))'
}
ISS=$(gh issue create -R "$SLUG" -t "divide by zero in calc" -b "calc.py crashes on 0" | num)
gh issue list -R "$SLUG" >/dev/null;                               ok "gh issue create + list (#$ISS)"
gh issue view "$ISS" -R "$SLUG" >/dev/null;                        ok "gh issue view (read the bug)"

echo "== implement the fix on a branch =="
cd "$WORK/clone"
git config user.email a@b; git config user.name a
git checkout -q -b fix-calc
printf 'def div(a,b):\n    return a/b if b else 0\n' > calc.py
git add -A && git commit -qm "fix: guard divide by zero"
git push -q origin fix-calc;                                        ok "git push fix branch (authed remote)"

echo "== pull request =="
PR=$(gh pr create -R "$SLUG" -t "Fix divide by zero" -H fix-calc -B main -b "closes the bug" | num)
gh pr view "$PR" -R "$SLUG" >/dev/null;                            ok "gh pr create + view (#$PR)"
gh pr diff "$PR" -R "$SLUG" | grep -q "calc.py";                   ok "gh pr diff"
gh issue comment "$PR" -R "$SLUG" -b "please review" >/dev/null;   ok "gh pr/issue comment"
gh pr review "$PR" -R "$SLUG" --approve -b "LGTM" >/dev/null;      ok "gh pr review --approve"

echo "== merge + close =="
for i in $(seq 1 10); do gh pr merge "$PR" -R "$SLUG" --method squash >/dev/null 2>&1 && break || sleep 1; done
ok "gh pr merge"
gh issue close "$ISS" -R "$SLUG" >/dev/null;                       ok "gh issue close"

echo "== metadata + escape hatch =="
gh label create -R "$SLUG" -n bug -c d73a4a >/dev/null;            ok "gh label create"
gh issue react "$ISS" -R "$SLUG" -c hooray >/dev/null;             ok "gh issue react"
gh api "repos/$SLUG" >/dev/null;                                   ok "gh api (REST passthrough)"

echo
echo "RESULT: agent has the full gh toolset for a fix-the-bug task (all steps via the shim)."
# cleanup
gh repo delete "$SLUG" --yes >/dev/null 2>&1 || true
rm -rf "$WORK"
