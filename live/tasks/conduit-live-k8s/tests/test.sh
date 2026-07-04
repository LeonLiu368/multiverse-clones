#!/usr/bin/env bash
# Harbor/Oddish test entrypoint. Runs the soak/SLO verifier against the live
# conduit deployment (in-cluster, reached via the k3s NodePort) AFTER the agent
# has exited, and writes reward.txt.
#
# Delegates to run_verifier.sh (which wraps soak.py) with this task's calibrated
# soak_config.json, targeting the SUT at the k3s NodePort on the task network.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export SOAK_TARGET="${SOAK_TARGET:-http://k3s:30800}"
export SOAK_CONFIG="${SOAK_CONFIG:-$HERE/soak_config.json}"
export FINDINGS_PATH="${FINDINGS_PATH:-/workspace/findings.json}"
# Snapshot the final deploy config for the result.json audit trail (recorded, not
# trusted for grade): the conduit Deployment's env as k3s sees it.
export AUDIT_CMD="${AUDIT_CMD:-kubectl -n conduit get deploy/conduit -o jsonpath='{.spec.template.spec.containers[0].env}'}"

exec "$HERE/run_verifier.sh"
