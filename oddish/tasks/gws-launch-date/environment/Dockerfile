# Agent (`main`) — the gworkspace-service image (ships gws-cli + gws-mcp) + pytest +
# the codebase. The seeded Workspace lives only in the `gworkspace` service.
FROM ghcr.io/abundant-ai/gworkspace-service:latest

RUN pip install --no-cache-dir pytest
COPY codebase /app
RUN ln -sf "$(command -v python3)" /usr/local/bin/python

WORKDIR /app
ENV GWS_API_URL=http://gworkspace:8080 \
    GWS_TOKEN=gws-clone-token
ENTRYPOINT []
CMD ["sleep", "infinity"]
