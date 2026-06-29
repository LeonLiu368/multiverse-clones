#!/usr/bin/env bash
set -uo pipefail
gh repo create webapp2 -d "web app" >/dev/null 2>&1 || true
gh milestone create -R acme/webapp2 -t v1.0 -d "first release" >/dev/null 2>&1 || true
gh issue create -R acme/webapp2 -t "Release blocker: crash on empty cart checkout" -b "Must be fixed and verified before we can ship v1.0." >/dev/null 2>&1 || true
