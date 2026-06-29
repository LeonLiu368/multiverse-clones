#!/usr/bin/env bash
set -uo pipefail
gh repo create inbox -d "issue inbox" >/dev/null 2>&1 || true
gh issue create -R acme/inbox -t "App crashes on null username at login" -b "NullPointerException in auth.py" >/dev/null 2>&1 || true
gh issue create -R acme/inbox -t "Security: API key printed to debug logs" -b "keys visible in /var/log/app.log" >/dev/null 2>&1 || true
gh issue create -R acme/inbox -t "App crashes on null username at login" -b "happens to me too" >/dev/null 2>&1 || true
gh issue create -R acme/inbox -t "Update copyright year in the footer" -b "minor cosmetic" >/dev/null 2>&1 || true
