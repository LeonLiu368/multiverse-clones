#!/usr/bin/env bash
set -uo pipefail
gh repo create tracker -d "issue tracker" >/dev/null 2>&1 || true
