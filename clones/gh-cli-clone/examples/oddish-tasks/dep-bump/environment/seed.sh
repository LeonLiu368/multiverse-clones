#!/usr/bin/env bash
set -uo pipefail
gh repo create api -d "api service" >/dev/null 2>&1 || true
gh api repos/acme/api/contents/requirements.txt -X POST \
  -f content="$(printf 'flask==2.0.1\nrequests==2.20.0\n' | base64 -w0)" \
  -f message="add requirements" -f branch=main >/dev/null 2>&1 || true
