#!/usr/bin/env bash
set -uo pipefail
# Base repo with a CI workflow (for the Actions commands) and an open issue.
gh repo create svc -d "coverage service" >/dev/null 2>&1 || true
gh api repos/acme/svc/contents/app.py -X POST \
  -f content="$(printf 'def add(a, b):\n    return a + b\n' | base64 -w0)" \
  -f message="seed app" -f branch=main >/dev/null 2>&1 || true
WF=$(printf 'name: build\non: [workflow_dispatch]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: mkdir -p out && echo COVCODE-7Q > out/code.txt\n      - uses: https://github.com/actions/upload-artifact@v3\n        with:\n          name: build-out\n          path: out/code.txt\n' | base64 -w0)
gh api repos/acme/svc/contents/.github/workflows/build.yml -X POST \
  -f content="$WF" -f message="add ci" -f branch=main >/dev/null 2>&1 || true
gh issue create -R acme/svc -t "Track: project setup" -b "Set up and operate the service." >/dev/null 2>&1 || true
