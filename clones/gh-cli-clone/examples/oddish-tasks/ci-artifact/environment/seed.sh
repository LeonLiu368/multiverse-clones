#!/usr/bin/env bash
set -uo pipefail
gh repo create service -d "service with CI" >/dev/null 2>&1 || true
WF=$(printf 'name: build\non: [workflow_dispatch]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: mkdir -p out && echo DEPLOY-4F2A > out/deploy.txt\n      - uses: https://github.com/actions/upload-artifact@v3\n        with:\n          name: deploy-code\n          path: out/deploy.txt\n' | base64 -w0)
gh api repos/acme/service/contents/.github/workflows/build.yml -X POST -f content="$WF" -f message="add ci" -f branch=main >/dev/null 2>&1 || true
