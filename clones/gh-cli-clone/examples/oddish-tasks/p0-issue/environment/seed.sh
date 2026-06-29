#!/usr/bin/env bash
set -uo pipefail
gh repo create app -d "app repo" >/dev/null 2>&1 || true
