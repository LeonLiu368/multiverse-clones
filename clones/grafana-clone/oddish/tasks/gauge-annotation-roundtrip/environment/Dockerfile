# Agent (`main`) container — Harbor builds this automatically as the agent's image.
#
# Thin grafana-agent: ships ONLY the `gcx` CLI and `mcp-grafana` MCP server (both thin HTTP
# clients) + the pure `grafana.server.links` helper they import. The gateway's API server,
# query engine, state/seed loader, and admin plane are STRIPPED, and the `grafanactl` admin
# CLI is intentionally absent. No fixture, no DB: the agent reaches the observability
# corpus only through the tools, pointed at the `grafana` service via GRAFANA_URL.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH=/opt/grafanacli \
    GRAFANA_URL=http://grafana \
    GRAFANA_TOKEN=test-token-acme-eval \
    GRAFANA_SERVICE_ACCOUNT_TOKEN=test-token-acme-eval

WORKDIR /opt/grafanacli
COPY grafana ./grafana
COPY bin/gcx bin/mcp-grafana /usr/local/bin/

# Strip the gateway's API + seed/query/admin source; keep only the CLI/MCP packages and the
# pure `grafana.server.links` helper. After this, `import grafana.server.state` raises and no
# api/seed source survives, while `gcx`/`mcp-grafana` still load.
RUN chmod +x /usr/local/bin/gcx /usr/local/bin/mcp-grafana && \
    find /opt/grafanacli/grafana/server -type f -name '*.py' \
        ! -name '__init__.py' ! -name 'links.py' -delete && \
    find /opt/grafanacli -name '__pycache__' -type d -prune -exec rm -rf {} + && \
    python -c "import grafana.cli.gcx, grafana.cli.mcp_server" && \
    ! python -c "import grafana.server.state" 2>/dev/null && \
    test ! -e /opt/grafanacli/grafana/server/state.py && \
    echo "thin grafana-agent OK (server api/seed stripped; gcx + mcp-grafana load)"

WORKDIR /home/agent
CMD ["sleep", "infinity"]
