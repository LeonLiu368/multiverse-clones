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

# Cluster-state dump (captured in test-stdout.txt): when the soak reports the
# target dead, THIS names the cause (ImagePullBackOff vs ContainerCreating vs
# CrashLoop vs stuck rollout) instead of leaving another blind infra_error.
if command -v kubectl >/dev/null 2>&1; then
  echo "===== cluster state (pre-soak) ====="
  kubectl get nodes -o wide 2>&1 | sed 's/^/  /'
  kubectl get pods -A -o wide 2>&1 | sed 's/^/  /'
  echo "----- non-ready pod details -----"
  kubectl get pods -A --no-headers 2>/dev/null | awk '$4!="Running" && $4!="Completed" {print $1" "$2}' |     while read -r ns pod; do
      echo "--- describe $ns/$pod (tail) ---"
      kubectl -n "$ns" describe pod "$pod" 2>&1 | tail -15 | sed 's/^/  /'
    done
  echo "----- recent events -----"
  kubectl get events -A --sort-by=.lastTimestamp 2>&1 | tail -20 | sed 's/^/  /'
  echo "===== end cluster state ====="
fi

exec "$HERE/run_verifier.sh"
