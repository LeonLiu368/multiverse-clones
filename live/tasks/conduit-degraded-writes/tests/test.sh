#!/usr/bin/env bash
# Harbor/Oddish test entrypoint. Runs the soak/SLO verifier against the live
# conduit deployment AFTER the agent has exited, and writes reward.txt.
#
# Delegates to run_verifier.sh (which wraps live/verifier/soak.py) with this
# task's calibrated soak_config.json, targeting the SUT on the task network.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export SOAK_TARGET="${SOAK_TARGET:-http://conduit.web.1:8000}"
export SOAK_CONFIG="${SOAK_CONFIG:-$HERE/soak_config.json}"
export FINDINGS_PATH="${FINDINGS_PATH:-/workspace/findings.json}"
# Snapshot the final deploy config for the result.json audit trail (recorded, not trusted).
export AUDIT_CMD="${AUDIT_CMD:-ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /root/.ssh/agent_key dokku@dokku config:show conduit}"

exec "$HERE/run_verifier.sh"
