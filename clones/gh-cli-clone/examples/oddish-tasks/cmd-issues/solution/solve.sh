#!/usr/bin/env bash
set -euo pipefail
R=acme/tracker
gh label create -R $R -n bug -c d73a4a -d "defect"
gh label create -R $R -n duplicate -c cccccc -d "dup"
gh milestone create -R $R -t v1.0 -d "first release"
N=$(gh issue create -R $R -t "Login fails" -b "repro steps" | grep -oE '[0-9]+$')
gh issue comment "$N" -R $R -b "looking into this"
gh issue react "$N" -R $R -c eyes
gh issue edit "$N" -R $R -t "Login fails on Safari"
gh issue close "$N" -R $R
gh issue reopen "$N" -R $R
LID=$(gh api "repos/$R/labels" | python3 -c 'import sys,json;print([l["id"] for l in json.load(sys.stdin) if l["name"]=="duplicate"][0])')
gh label delete "$LID" -R $R
gh repo create scratch -d tmp >/dev/null
gh repo delete acme/scratch --yes
gh repo rename $R tracker-v2
