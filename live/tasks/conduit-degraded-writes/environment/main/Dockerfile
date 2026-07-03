# main (agent) image — thin on-call SWE agent. Ships the tools to DIAGNOSE from
# live telemetry and REMEDIATE the live deployment, and NO answer material:
#   - logfire CLI + logfire-mcp (client-only: cli.py + mcp_server.py, NOT server.py
#     -> the corpus/API is not greppable or recomputable here)
#   - ssh (the dokku agent surface), git, curl, httpx, jq
#   - the provisioned agent SSH private key (mounted at runtime from the keys volume)
# No remediation knob or answer material is baked here or in the instruction —
# diagnosis is the task.
FROM python:3.12-slim

RUN pip install --no-cache-dir httpx mcp \
    && apt-get update \
    && apt-get install -y --no-install-recommends openssh-client git curl jq ca-certificates \
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
    LOGFIRE_URL=http://logfire:80 \
    LOGFIRE_MIN_TIMESTAMP=2026-07-01T00:00:00Z \
    WORKSPACE=/workspace
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/agent-entrypoint.sh"]
CMD ["sleep", "infinity"]
