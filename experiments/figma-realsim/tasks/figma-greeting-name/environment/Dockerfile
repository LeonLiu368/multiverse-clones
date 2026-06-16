# Agent (`main`) container — the public figma-service image (ships figma-cli + figma-mcp)
# plus pytest and the codebase. No figma source vendored into the task; the seeded
# design (a REAL imported Figma file) lives only in the `figma` service.
FROM ghcr.io/abundant-ai/figma-service:latest

RUN pip install --no-cache-dir pytest
COPY codebase /app
RUN ln -sf "$(command -v python3)" /usr/local/bin/python

WORKDIR /app
ENV FIGMA_API_URL=http://figma:3000 \
    FIGMA_TOKEN=figma-clone-token \
    FIGMA_FILE_KEY=BM8JZIS9LbZnEZSUQit8T0
ENTRYPOINT []
CMD ["sleep", "infinity"]
