#!/usr/bin/env bash
set -euo pipefail
gh label create -R ghc-admin/triage -n wontfix -c b60205 -d "won't fix"
gh issue comment 1 -R ghc-admin/triage -b "closing as wontfix"
gh issue close 1 -R ghc-admin/triage
