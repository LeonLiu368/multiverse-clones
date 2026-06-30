#!/usr/bin/env sh
set -eu

exec python -m grafana.server.app
