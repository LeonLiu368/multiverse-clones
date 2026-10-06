#!/usr/bin/env bash
set -euo pipefail
cd /app/repo
go test ./params -count=1 -v
