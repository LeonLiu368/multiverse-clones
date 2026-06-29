#!/usr/bin/env bash
set -euo pipefail
R=acme/webapp2
ISS=$(gh api "repos/$R/issues?type=issues&limit=50" | python3 -c 'import sys,json;print([i["number"] for i in json.load(sys.stdin) if "blocker" in i["title"].lower()][0])')
gh issue close "$ISS" -R $R
gh milestone close v1.0 -R $R
gh release create v1.0 -R $R -t "v1.0" -n "First stable release."
