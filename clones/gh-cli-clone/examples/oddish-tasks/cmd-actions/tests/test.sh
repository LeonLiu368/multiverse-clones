#!/usr/bin/env bash
# Pass iff the agent opened an issue titled exactly "build.yml" (requires it to
# have run `gh workflow list` to discover the name) in acme/pipeline.
set -uo pipefail; mkdir -p /logs/verifier
ok=$(gh api "repos/acme/pipeline/issues?type=issues&state=all&limit=50" 2>/dev/null | python3 -c 'import sys,json;print(int(any(i.get("title")=="build.yml" for i in json.load(sys.stdin))))' 2>/dev/null || echo 0)
[ "$ok" = 1 ] && echo 1 >/logs/verifier/reward.txt || echo 0 >/logs/verifier/reward.txt
echo "issue_build_yml=$ok -> $(cat /logs/verifier/reward.txt)"
