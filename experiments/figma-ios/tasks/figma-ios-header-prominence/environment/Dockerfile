# Agent (`main`) — thin figma-agent (figma-cli + figma-mcp, no server/seed source) + pytest + codebase.
FROM ghcr.io/abundant-ai/figma-agent:latest
RUN pip install --no-cache-dir pytest
COPY codebase /app
RUN ln -sf "$(command -v python3)" /usr/local/bin/python
WORKDIR /app
ENV FIGMA_API_URL=http://figma:3000 FIGMA_TOKEN=figma-clone-token FIGMA_FILE_KEY=R1jno9FuCgYkNXayz8zglW
ENTRYPOINT []
CMD ["sleep", "infinity"]
