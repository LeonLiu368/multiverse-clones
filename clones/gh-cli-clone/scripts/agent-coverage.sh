#!/usr/bin/env bash
# Exhaustive coverage of EVERY agent-facing ghc command, exercised through the
# `gh` shim (the exact interface an agent uses) against the offline forge.
# Prints a per-command ✓/✗ table and a summary; exits non-zero if anything fails.
#
#   GHC_HOST=http://localhost:3300 GHC_TOKEN=$(cat ghc-token.txt) bash scripts/agent-coverage.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HERE:$PATH"                       # `gh` == our shim -> ghc
export GHC_HOST="${GHC_HOST:-http://localhost:3300}"
export GHC_TOKEN="${GHC_TOKEN:-$(cat "$HERE/../ghc-token.txt")}"
GHC="$HERE/../.venv/bin/ghc"

PASS=0; FAIL=0; ROWS=""
# `ghc create` faithfully prints the resource URL (e.g.
# http://10.88.0.2/acme/webapp/issues/3) — like real gh — NOT "#3". Extract the
# trailing path number; fall back to a "#N" form if one is ever present.
lastnum() { grep -oE '([0-9]+)[[:space:]]*$|#[0-9]+' | tail -1 | grep -oE '[0-9]+'; }
chk() {  # chk "<label>" <cmd...>   — pass if exit 0
  local label="$1"; shift
  if "$@" >/tmp/cov.out 2>&1; then ROWS+="  ✓ $label\n"; PASS=$((PASS+1));
  else ROWS+="  ✗ $label  -- $(tail -1 /tmp/cov.out)\n"; FAIL=$((FAIL+1)); fi
}
chkout() {  # chkout "<label>" "<grep>" <cmd...>  — pass if exit 0 AND output matches
  local label="$1" pat="$2"; shift 2
  if "$@" >/tmp/cov.out 2>&1 && grep -q "$pat" /tmp/cov.out; then ROWS+="  ✓ $label\n"; PASS=$((PASS+1));
  else ROWS+="  ✗ $label  -- $(tail -1 /tmp/cov.out)\n"; FAIL=$((FAIL+1)); fi
}

ME=$(gh api user 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["login"])')
R="cov-$$"; SLUG="$ME/$R"
WORK=$(mktemp -d)

echo "== AUTH =="
chkout "auth status"           "$ME"        gh auth status
chkout "auth token"            "."          gh auth token

echo "== REPO =="
chkout "repo create"           "$R"         gh repo create "$R" -d "coverage repo"
chkout "repo view"             "$SLUG"      gh repo view "$SLUG"
chk    "repo view --json"                   bash -c "gh repo view $SLUG --json | python3 -c 'import sys,json;json.load(sys.stdin)'"
chk    "repo list"                          gh repo list
chk    "repo edit (desc+topics)"            gh repo edit "$SLUG" -d "edited" --topics "a,b"
chk    "repo clone"                         gh repo clone "$SLUG" "$WORK/clone"
chk    "repo rename"                        gh repo rename "$SLUG" "${R}-renamed"
chk    "repo rename (back)"                 gh repo rename "$ME/${R}-renamed" "$R"

echo "== ISSUE =="
ISS=$(gh issue create -R "$SLUG" -t "bug one" -b "body" | lastnum)
chk    "issue create (#$ISS)"               test -n "$ISS"
chk    "issue list"                         gh issue list -R "$SLUG"
chk    "issue list --state all"             gh issue list -R "$SLUG" --state all
chkout "issue view"            "bug one"     gh issue view "$ISS" -R "$SLUG"
chk    "issue edit"                         gh issue edit "$ISS" -R "$SLUG" -t "bug one (edited)"
chk    "issue comment"                      gh issue comment "$ISS" -R "$SLUG" -b "a comment"
chk    "issue view --comments"              gh issue view "$ISS" -R "$SLUG" --comments
chk    "issue react"                        gh issue react "$ISS" -R "$SLUG" -c rocket
chk    "issue close"                        gh issue close "$ISS" -R "$SLUG"
chk    "issue reopen"                       gh issue reopen "$ISS" -R "$SLUG"

echo "== LABEL / MILESTONE =="
chkout "label create"          "P1bug"      gh label create -R "$SLUG" -n P1bug -c d73a4a -d "x"
chkout "label list"            "P1bug"      gh label list -R "$SLUG"
LID=$(gh label list -R "$SLUG" --json | python3 -c 'import sys,json;print([l["id"] for l in json.load(sys.stdin) if l["name"]=="P1bug"][0])')
chk    "label delete"                       gh label delete "$LID" -R "$SLUG"
chkout "milestone create"      "v1"         gh milestone create -R "$SLUG" -t v1 -d "rel"
chkout "milestone list"        "v1"         gh milestone list -R "$SLUG"

echo "== PR =="
# make a divergent branch + commit so a PR is real
cd "$WORK/clone"
git checkout -q -b feature
printf 'hello\n' > FEATURE.txt
git add -A && git commit -qm "add feature"
git push -q origin feature
PR=$(gh pr create -R "$SLUG" -t "Add feature" -H feature -B main -b "the feature" | lastnum)
chk    "pr create (#$PR)"                   test -n "$PR"
chk    "pr list"                            gh pr list -R "$SLUG"
chkout "pr view"               "Add feature" gh pr view "$PR" -R "$SLUG"
chkout "pr diff"               "FEATURE.txt" gh pr diff "$PR" -R "$SLUG"
chk    "pr checkout"                         bash -c "cd $WORK/clone && git checkout -q main && gh pr checkout $PR -R $SLUG"
chk    "pr review --approve"                gh pr review "$PR" -R "$SLUG" --approve -b ok
# Forgejo computes mergeability async -> retry, then confirm via the PR's merged flag.
for i in $(seq 1 10); do gh pr merge "$PR" -R "$SLUG" --method squash >/dev/null 2>&1 && break || sleep 1; done
chk    "pr merge"                           bash -c "gh pr view $PR -R $SLUG --json | python3 -c 'import sys,json;assert json.load(sys.stdin)[\"merged\"]'"
# a second PR to exercise close/reopen
cd "$WORK/clone"; git checkout -q main; git checkout -q -b feature2
printf 'x\n' > F2.txt; git add -A && git commit -qm f2; git push -q origin feature2
PR2=$(gh pr create -R "$SLUG" -t "Second" -H feature2 -B main -b x | lastnum)
chk    "pr close"                           gh pr close "$PR2" -R "$SLUG"
chk    "pr reopen"                          gh pr reopen "$PR2" -R "$SLUG"

echo "== ACTIONS (workflow/run) =="
# push a workflow file to main (sync first: the squash merge advanced remote main)
cd "$WORK/clone"; git checkout -q main; git fetch -q origin main; git reset -q --hard origin/main
mkdir -p .forgejo/workflows
printf 'name: CI\non: [push]\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n' > .forgejo/workflows/ci.yml
git add -A && git commit -qm "add workflow"; git push -q origin main
chkout "workflow list"         "ci.yml"     gh workflow list -R "$SLUG"
chk    "workflow run (dispatch)"            gh workflow run ci.yml -R "$SLUG" --ref main
chk    "run list"                           gh run list -R "$SLUG"

echo "== API (escape hatch) =="
chkout "api GET"               "$R"         gh api "repos/$SLUG"
chk    "api --paginate"                     gh api "repos/$SLUG/issues" --paginate
chk    "api graphql guarded"                bash -c "! gh api graphql 2>/dev/null"

echo "== FORK (into org) =="
gh api orgs -X POST -f username="ghc-org-$$" >/dev/null 2>&1 || true
"$GHC" api "orgs" >/dev/null 2>&1 || true
# create org via admin API then fork
gh api "admin/users" >/dev/null 2>&1 || true
ORG="covorg$$"
gh api "orgs" -X POST -f username="$ORG" -f visibility=public >/dev/null 2>&1 \
  || gh api "admin/users/$ME/orgs" >/dev/null 2>&1 || true
if gh api "orgs/$ORG" >/dev/null 2>&1; then
  chk  "repo fork (into org)"               gh repo fork "$SLUG" --org "$ORG"
else
  ROWS+="  ~ repo fork  -- skipped (no org; fork-to-self is a name conflict)\n"
fi

# cleanup
gh repo delete "$SLUG" --yes >/dev/null 2>&1 || true
rm -rf "$WORK"

echo
echo -e "$ROWS"
echo "================================================"
echo "COVERAGE: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "ALL agent-facing commands work." || echo "Some commands failed."
exit "$FAIL"
