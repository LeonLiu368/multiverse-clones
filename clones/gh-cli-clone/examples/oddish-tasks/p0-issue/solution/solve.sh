#!/usr/bin/env bash
set -euo pipefail
N=$(gh issue create -R acme/app -t "TASK-DONE" -b "done" | grep -oE '[0-9]+$')
gh issue comment "$N" -R acme/app -b "working on it"
gh issue close "$N" -R acme/app
