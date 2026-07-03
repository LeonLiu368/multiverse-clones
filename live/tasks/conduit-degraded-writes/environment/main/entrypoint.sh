#!/bin/sh
# Agent entrypoint. Installs the provisioned agent SSH key for the dokku surface,
# then (as a fallback for Harbors that don't honor service_completed_successfully)
# waits until provisioning is done: the readiness marker exists AND conduit is
# healthy. Then hands off to the agent's command (default: sleep infinity).
set -e

# Install the agent SSH private key (mounted read-only from the shared keys volume).
if [ -f /mnt/keys/agent_key ]; then
  mkdir -p /root/.ssh
  cp /mnt/keys/agent_key /root/.ssh/agent_key
  chmod 600 /root/.ssh/agent_key
  cat > /root/.ssh/config <<'EOF'
Host dokku
  HostName dokku
  User dokku
  IdentityFile /root/.ssh/agent_key
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR
EOF
  chmod 600 /root/.ssh/config
fi

# Wait for provisioning: marker in the shared state volume + conduit healthy.
MARKER=/mnt/state/provisioned
CONDUIT="http://conduit.web.1:8000/api/tags"
i=0
while [ "$i" -lt 180 ]; do
  if [ -f "$MARKER" ] && curl -fsS -m3 "$CONDUIT" >/dev/null 2>&1; then
    echo "[agent-entrypoint] provisioning complete; conduit healthy. ready."
    break
  fi
  i=$((i+1)); sleep 2
done

exec "$@"
