#!/usr/bin/env bash
set -euo pipefail
gh label create -R acme/triage -n wontfix -c b60205 -d "won't fix"
gh issue comment 1 -R acme/triage -b "closing as wontfix"
gh issue close 1 -R acme/triage
