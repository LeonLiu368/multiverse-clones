#!/bin/bash
# Oracle: retrieve the current staging Postgres host:port from #infra and answer the
# question in #ask-platform with it.
set -euo pipefail
slack-cli post ask-platform "The current staging Postgres is at pg-staging.globex.internal:6432 (pgbouncer port). The pg-staging-legacy host was decommissioned — don't use it."
echo "oracle posted staging Postgres host to #ask-platform"
