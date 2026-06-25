# Agent (`main`) — the THIN gworkspace-agent image (ships gws-cli + gws-mcp ONLY,
# no api/ or seed/ source, no fixtures) + pytest + the codebase. The seeded
# Workspace lives only in the `gworkspace` service; the agent reaches it via tools.
FROM ghcr.io/abundant-ai/gworkspace-agent:latest

RUN pip install --no-cache-dir pytest
COPY codebase /app
RUN ln -sf "$(command -v python3)" /usr/local/bin/python

WORKDIR /app
ENV GWS_API_URL=http://gworkspace:8080 \
    GWS_TOKEN=gws-clone-token
ENTRYPOINT []
CMD ["sleep", "infinity"]
