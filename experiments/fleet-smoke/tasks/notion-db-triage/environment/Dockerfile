# Agent (`main`) container — Harbor builds this automatically as the agent's image.
# Neutral python:slim base. Ships ONLY the agent's tools (notion-cli + the notion-mcp
# MCP server, from the vendored notionclone package) — NO API server source, NO seed
# system, NO corpus. The agent reaches the workspace only through the tools, pointed
# at the `notion` gateway via NOTION_API_URL. A build-time smoke test strips and
# asserts the absence of api/ and seed/ so no answer key is greppable here (R2.k).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

# vendored package (code only) -> provides `notion-cli` and `notion-mcp`. pytest too,
# so the verifier can run inside this container if needed. Build from a /tmp copy and
# DELETE it after install so NO server/seed SOURCE tree survives at /opt (R2.k). The
# install lands in site-packages, where we strip api/ + seed/. Leaving the source at
# /opt was the leak the dogfood auditor exploited: `import notionclone.seed.generator`
# recomputes the answer even when a literal grep finds nothing.
COPY notionclone /tmp/notionclone-src
RUN pip install --no-cache-dir "/tmp/notionclone-src[mcp]" pytest && \
    PKG="$(python -c 'import notionclone, os; print(os.path.dirname(notionclone.__file__))')" && \
    rm -rf "$PKG/api" "$PKG/seed" /tmp/notionclone-src && \
    test ! -e "$PKG/api" && test ! -e "$PKG/seed" && test ! -e /tmp/notionclone-src && \
    ! python -c "import notionclone.seed" 2>/dev/null && \
    ! python -c "import notionclone.api"  2>/dev/null && \
    notion-cli --help >/dev/null && \
    python -c "import notionclone.cli.main, notionclone.mcp.server, notionclone.client" && \
    echo "thin notion agent OK (no api/, no seed/ source; generator not importable)"

ENV NOTION_API_URL=http://notion:3000 \
    NOTION_TOKEN=notion-clone-token \
    CLONE_STATE_PATH=/srv/notion.db
WORKDIR /workspace
CMD ["sleep", "infinity"]
