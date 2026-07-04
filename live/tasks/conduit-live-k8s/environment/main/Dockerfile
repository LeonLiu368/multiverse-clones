# main (agent) image — thin on-call SWE agent for the k3s-plane conduit task.
# Ships the tools to DIAGNOSE from live telemetry and REMEDIATE the live
# deployment, and NO answer material:
#   - kubectl (the deploy surface: `kubectl -n conduit set env deploy/conduit ...`),
#     kubeconfig assembled at runtime from the k3s shared volume (server rewritten
#     127.0.0.1:6443 -> k3s:6443).
#   - logfire CLI + logfire-mcp (client-only: cli.py + mcp_server.py, NOT server.py
#     -> the corpus/API is not greppable or recomputable here).
#   - httpx, curl, jq.
# No remediation knob or answer material is baked here or in the instruction —
# diagnosis is the task. (No WEB_CONCURRENCY / "4" / "worker" anywhere.)
FROM python:3.12-slim

ARG KUBECTL_VERSION=v1.31.5
RUN pip install --no-cache-dir httpx mcp \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl jq ca-certificates \
    && arch="$(dpkg --print-architecture)" \
    && case "$arch" in amd64) K=amd64;; arm64) K=arm64;; *) K="$arch";; esac \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${K}/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && kubectl version --client=true \
    && rm -rf /var/lib/apt/lists/*

# logfire client (thin) — server.py deliberately omitted (anti-leak).
RUN mkdir -p /opt/logfire_clone
COPY main/logfire_client/__init__.py   /opt/logfire_clone/__init__.py
COPY main/logfire_client/cli.py        /opt/logfire_clone/cli.py
COPY main/logfire_client/mcp_server.py /opt/logfire_clone/mcp_server.py
RUN printf '#!/bin/sh\nexec python -m logfire_clone.cli "$@"\n'        > /usr/local/bin/logfire     && chmod +x /usr/local/bin/logfire \
 && printf '#!/bin/sh\nexec python -m logfire_clone.mcp_server "$@"\n' > /usr/local/bin/logfire-mcp && chmod +x /usr/local/bin/logfire-mcp

COPY main/entrypoint.sh /usr/local/bin/agent-entrypoint.sh
RUN chmod +x /usr/local/bin/agent-entrypoint.sh

ENV PYTHONPATH=/opt \
    KUBECONFIG=/root/.kube/config \
    LOGFIRE_URL=http://k3s:30080 \
    LOGFIRE_TOKEN=task-read-token \
    LOGFIRE_MIN_TIMESTAMP=2026-07-01T00:00:00Z \
    WORKSPACE=/workspace
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/agent-entrypoint.sh"]
CMD ["sleep", "infinity"]
