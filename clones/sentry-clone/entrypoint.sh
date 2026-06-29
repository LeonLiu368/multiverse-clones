#!/usr/bin/env sh
set -eu

exec python -m sentry_clone.server.app
