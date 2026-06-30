# Agent (`main`) — the THIN gworkspace-agent image (gws-cli + gws-mcp ONLY, no api/
# or seed/ source, no fixtures). The seeded Workspace lives only in `gworkspace`; the
# agent reaches it via tools, and creates the event via the calendar WRITE tool.
FROM ghcr.io/abundant-ai/gworkspace-agent:latest

RUN pip install --no-cache-dir pytest
COPY codebase /app
RUN ln -sf "$(command -v python3)" /usr/local/bin/python

WORKDIR /app
ENV GWS_API_URL=http://gworkspace:8080 \
    GWS_TOKEN=gws-clone-token
ENTRYPOINT []
CMD ["sleep", "infinity"]
