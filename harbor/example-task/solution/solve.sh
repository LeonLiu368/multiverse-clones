#!/bin/bash
# Oracle: post the correct root-cause summary to #incidents.
set -euo pipefail
slack-cli post incidents "ROOT CAUSE: connection pool exhaustion — the v2.3 deploy raised worker concurrency 4x without increasing the DB connection pool, so requests queue waiting for a free connection."
echo "oracle posted root cause to #incidents"
