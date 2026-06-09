# Agent (`main`) container. It is the prebuilt, PUBLIC figma-service image — which
# already ships `figma-cli` + the `figma-mcp` MCP server — with pytest and the task
# codebase added on top. NO figma source is vendored into the task; the tools come
# from the pulled image, and the only task-owned files here are the codebase. The
# seeded design data lives ONLY in the `figma` service (mounted there), so the agent
# can reach the spec solely through the API — running as root in `main` leaks nothing
# (there is no secret here), and it lets Harbor's root-owned solution/verifier uploads
# be chmod'd and executed.
FROM ghcr.io/abundant-ai/figma-service:latest

RUN pip install --no-cache-dir pytest

# the codebase the agent edits (the figma-service base already has figma-cli/figma-mcp)
COPY codebase /app
RUN ln -sf "$(command -v python3)" /usr/local/bin/python

WORKDIR /app
ENV FIGMA_API_URL=http://figma:3000 \
    FIGMA_TOKEN=figma-clone-token \
    FIGMA_FILE_KEY=BtnStatesSpecFile0001x
# Reset the figma-service image's serve-the-API entrypoint; `main` is just the agent box.
ENTRYPOINT []
CMD ["sleep", "infinity"]
