# Agent (`main`) container — Harbor builds this automatically as the agent's image.
# It ships ONLY the agent's tools (figma-cli + the figma-mcp MCP server, from the
# vendored figmaclone package) and the codebase at /workspace. No fixture, no DB:
# the agent can reach the design file only through the tools, pointed at the
# `figma` service via FIGMA_API_URL.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

# vendored package (code only) -> provides `figma-cli` and `figma-mcp`.
# pytest is installed too: the agent runs the visible tests, and the verifier runs
# pytest inside this container against the candidate code.
COPY figmaclone /opt/figmaclone
RUN pip install --no-cache-dir "/opt/figmaclone[mcp]" pytest

# the codebase the agent edits
COPY codebase /workspace

ENV FIGMA_API_URL=http://figma:3000 \
    FIGMA_TOKEN=figma-clone-token \
    FIGMA_FILE_KEY=Pr1cingCardSpecFile001
WORKDIR /workspace
