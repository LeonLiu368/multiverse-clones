# Agent (`main`): a base + the gauge tooling COPIED from the thin, data-free gauge-agent image.
# The checkout logs live ONLY in the `gauge` sidecar; this container reaches them over HTTP via gcx.
FROM --platform=linux/amd64 python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends bash git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/abundant-ai/gauge-agent:latest /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/
COPY --from=ghcr.io/abundant-ai/gauge-agent:latest /opt/gaugecli /opt/gaugecli
ENV PYTHONPATH=/opt/gaugecli GRAFANA_URL=http://gauge GRAFANA_TOKEN=test-token
COPY codebase /workspace
WORKDIR /workspace
CMD ["sleep", "infinity"]
