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
#
# Install from /tmp, then STRIP the gateway's API server (`api/`) and seed/generator
# (`seed/`) from the installed package — mirroring docker/Dockerfile.agent. The agent
# box must carry only the thin HTTP clients (figma-cli + figma-mcp); it must NOT be
# able to import the seed generator or grep the planted design spec out of disk. A
# build-time smoke test asserts the server/seed source is gone and the answer color
# (#1D4ED8) is nowhere on the agent image.
COPY figmaclone /tmp/figmaclone
RUN pip install --no-cache-dir "/tmp/figmaclone[mcp]" pytest && \
    PKG="$(python -c 'import figmaclone, os; print(os.path.dirname(figmaclone.__file__))')" && \
    rm -rf "$PKG/api" "$PKG/seed" && \
    rm -rf /tmp/figmaclone && \
    test ! -e "$PKG/api" && test ! -e "$PKG/seed" && \
    python -c "import figmaclone.cli.main, figmaclone.mcp.server" && \
    figma-cli --help >/dev/null && \
    ! python -c "import figmaclone.seed" 2>/dev/null && \
    ! grep -rsq '#1D4ED8' /opt /usr/local/lib/python*/site-packages/figmaclone && \
    echo "thin agent OK (no api/, no seed/; no #1D4ED8; figma-cli + figma-mcp load)"

# the codebase the agent edits
COPY codebase /workspace

ENV FIGMA_API_URL=http://figma:3000 \
    FIGMA_TOKEN=figma-clone-token \
    FIGMA_FILE_KEY=Pr1cingCardSpecFile001
WORKDIR /workspace
