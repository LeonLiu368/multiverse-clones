# Agent (`main`) container — Harbor builds this automatically as the agent's image.
#
# Thin gauge-agent: ships ONLY the `gcx` CLI and `mcp-grafana` MCP server (both thin HTTP
# clients) + the pure `gauge.server.links` helper they import. The gateway's API server,
# query engine, state/seed loader, and admin plane are STRIPPED, and the `gaugectl` admin
# CLI is intentionally absent. No fixture, no DB: the agent reaches the observability
# corpus only through the tools, pointed at the `gauge` service via GRAFANA_URL.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH=/opt/gaugecli \
    GRAFANA_URL=http://gauge \
    GRAFANA_TOKEN=test-token-acme-eval \
    GRAFANA_SERVICE_ACCOUNT_TOKEN=test-token-acme-eval

WORKDIR /opt/gaugecli
COPY gauge ./gauge
COPY bin/gcx bin/mcp-grafana /usr/local/bin/

# Strip the gateway's API + seed/query/admin source; keep only the CLI/MCP packages and the
# pure `gauge.server.links` helper. After this, `import gauge.server.state` raises and no
# api/seed source survives, while `gcx`/`mcp-grafana` still load.
RUN chmod +x /usr/local/bin/gcx /usr/local/bin/mcp-grafana && \
    find /opt/gaugecli/gauge/server -type f -name '*.py' \
        ! -name '__init__.py' ! -name 'links.py' -delete && \
    find /opt/gaugecli -name '__pycache__' -type d -prune -exec rm -rf {} + && \
    python -c "import gauge.cli.gcx, gauge.cli.mcp_server" && \
    ! python -c "import gauge.server.state" 2>/dev/null && \
    test ! -e /opt/gaugecli/gauge/server/state.py && \
    echo "thin gauge-agent OK (server api/seed stripped; gcx + mcp-grafana load)"

WORKDIR /home/agent
CMD ["sleep", "infinity"]
