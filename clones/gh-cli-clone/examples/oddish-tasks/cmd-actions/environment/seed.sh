#!/usr/bin/env bash
set -uo pipefail
gh repo create pipeline -d "ci" >/dev/null 2>&1 || true
WF=$(printf 'name: build\non: [workflow_dispatch]\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n' | base64 -w0)
gh api repos/acme/pipeline/contents/.github/workflows/build.yml -X POST \
  -f content="$WF" -f message="add workflow" -f branch=main >/dev/null 2>&1 || true
