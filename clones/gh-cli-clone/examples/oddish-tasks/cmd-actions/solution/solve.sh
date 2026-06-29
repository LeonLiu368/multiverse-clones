#!/usr/bin/env bash
set -euo pipefail
R=acme/pipeline
WF=$(gh workflow list -R $R | grep -oE '[^/ ]+\.ya?ml' | head -1)   # discover the name
gh workflow run "$WF" -R $R --ref main
gh run list -R $R
gh issue create -R $R -t "$WF" -b "dispatched the workflow"
