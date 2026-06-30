# Agent (`main`) container — Harbor force-builds this as the agent image.
# Ships ONLY the agent tools (`logfire` CLI + `logfire-mcp`) and the codebase at
# /workspace. NO records, NO gateway server.py: the corpus is reachable solely through
# the gateway over HTTP ($LOGFIRE_URL). `import logfire_clone.server` raises here.
FROM mirror.gcr.io/library/python:3.12-slim

RUN pip install --no-cache-dir mcp pytest \
    && apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

# Client-only package (no server.py / no seed source).
RUN mkdir -p /opt/logfire_clone
COPY logfire_clone/__init__.py   /opt/logfire_clone/__init__.py
COPY logfire_clone/cli.py        /opt/logfire_clone/cli.py
COPY logfire_clone/mcp_server.py /opt/logfire_clone/mcp_server.py

RUN printf '#!/bin/sh\nexec python -m logfire_clone.cli "$@"\n'        > /usr/local/bin/logfire     && chmod +x /usr/local/bin/logfire \
 && printf '#!/bin/sh\nexec python -m logfire_clone.mcp_server "$@"\n' > /usr/local/bin/logfire-mcp && chmod +x /usr/local/bin/logfire-mcp

# the codebase the agent edits
COPY codebase /workspace

ENV PYTHONPATH=/opt:/workspace \
    LOGFIRE_URL=http://logfire \
    LOGFIRE_TOKEN=test-token-acme-eval \
    LOGFIRE_MIN_TIMESTAMP=2026-06-24T00:00:00Z
WORKDIR /workspace
