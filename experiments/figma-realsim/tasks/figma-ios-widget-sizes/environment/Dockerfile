# Agent (`main`) container — the public figma-service image (figma-cli + figma-mcp)
# plus pytest and the codebase. No figma source vendored; the seeded design (a slice
# of the real "iOS and iPadOS 26 (Community)" file) lives only in the `figma` service.
FROM ghcr.io/abundant-ai/figma-service:latest

RUN pip install --no-cache-dir pytest
COPY codebase /app
RUN ln -sf "$(command -v python3)" /usr/local/bin/python

WORKDIR /app
ENV FIGMA_API_URL=http://figma:3000 \
    FIGMA_TOKEN=figma-clone-token \
    FIGMA_FILE_KEY=R1jno9FuCgYkNXayz8zglW
ENTRYPOINT []
CMD ["sleep", "infinity"]
