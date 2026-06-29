#!/usr/bin/env bash
# task seed: create the triage repo + an open issue #1
set -uo pipefail
gh repo create triage -d "triage demo" >/dev/null 2>&1 || true
gh issue create -R acme/triage -t "spammy issue" -b "please triage" >/dev/null 2>&1 || true
