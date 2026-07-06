#!/bin/sh
# Agent entrypoint (k3s plane). Assembles the kubeconfig from the k3s shared
# volume (rewriting the apiserver 127.0.0.1:6443 -> k3s:6443 so a sibling reaches
# the cluster), then waits until the environment is READY for the agent:
#   - k3s node Ready,
#   - the conduit SUT answering /api/tags via its NodePort (http://k3s:30800),
#   - live spans flowing (service_name='conduit' rows visible via logfire query).
# Then hands off to the agent's command (default: sleep infinity).
set -e

KUBE_SRC="${KUBE_SRC:-/mnt/kube/kubeconfig.yaml}"
KUBECONFIG="${KUBECONFIG:-/root/.kube/config}"
K3S_HOST="${K3S_HOST:-k3s}"
CONDUIT_URL="${CONDUIT_URL:-http://k3s:30800}"
LOGFIRE_URL="${LOGFIRE_URL:-http://k3s:30080}"
LOGFIRE_TOKEN="${LOGFIRE_TOKEN:-task-read-token}"

# 1. Assemble kubeconfig from the shared volume; rewrite the server to reach k3s
#    by service name (k3s writes 127.0.0.1:6443, valid only inside its container).
mkdir -p "$(dirname "$KUBECONFIG")"
echo "[agent-entrypoint] waiting for kubeconfig at $KUBE_SRC"
i=0
while [ ! -s "$KUBE_SRC" ]; do
  i=$((i+1)); [ "$i" -lt 120 ] || { echo "[agent-entrypoint] kubeconfig never appeared" >&2; break; }
  sleep 2
done
if [ -s "$KUBE_SRC" ]; then
  # Reach the apiserver by service name regardless of what host k3s baked in
  # (127.0.0.1 locally; the container/host IP on Daytona).
  sed -E "s#server: https://[^[:space:]]+#server: https://${K3S_HOST}:6443#g" "$KUBE_SRC" > "$KUBECONFIG"
  chmod 600 "$KUBECONFIG"
  echo "[agent-entrypoint] kubeconfig ready (server -> https://${K3S_HOST}:6443)"
fi

# 2. Wait for k3s node Ready.
echo "[agent-entrypoint] waiting for k3s node Ready"
i=0
while [ "$i" -lt 120 ]; do
  if kubectl get nodes 2>/dev/null | grep -q " Ready "; then
    echo "[agent-entrypoint] k3s node Ready"; break
  fi
  i=$((i+1)); sleep 2
done

# 3. Wait for the conduit SUT to answer via its NodePort.
echo "[agent-entrypoint] waiting for conduit at $CONDUIT_URL/api/tags"
i=0
while [ "$i" -lt 180 ]; do
  if curl -fsS -m3 "$CONDUIT_URL/api/tags" >/dev/null 2>&1; then
    echo "[agent-entrypoint] conduit healthy"; break
  fi
  i=$((i+1)); sleep 2
done

# 4. Drive a little load + wait for live spans to appear in logfire (so the
#    agent's very first query already sees telemetry).
echo "[agent-entrypoint] nudging load + waiting for live conduit spans in logfire"
i=0
while [ "$i" -lt 60 ]; do
  # a few requests to generate spans
  for _ in 1 2 3 4 5; do curl -s -o /dev/null -m3 "$CONDUIT_URL/api/articles" 2>/dev/null || true; done
  QBODY='{"sql":"SELECT count(*) c FROM records WHERE service_name = char(99,111,110,100,117,105,116)","min_timestamp":"2026-07-01T00:00:00Z"}'
  N=$(curl -s -m5 -X POST "$LOGFIRE_URL/v2/query" \
        -H "Authorization: Bearer $LOGFIRE_TOKEN" -H "Content-Type: application/json" \
        --data "$QBODY" 2>/dev/null \
        | grep -o '"c": *[0-9]*' | grep -o '[0-9]*' | head -1)
  if [ -n "$N" ] && [ "$N" -gt 0 ] 2>/dev/null; then
    echo "[agent-entrypoint] live conduit spans in logfire: $N — environment ready"; break
  fi
  i=$((i+1)); sleep 3
done

exec "$@"
