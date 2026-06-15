# Agent (`main`) container for a two-surface task: Figma + Linear.
# Base is the public figma-service image (ships figma-cli + figma-mcp); the Linear
# tools (`linear`/`jira`) are layered in from the ticketvector-service image. No
# service source is vendored into the task — only the codebase. Both backends are
# reached over the network (figma at :3000, ticketvector at :8765); the seeded
# design + ticket data live only in those service containers.
FROM ghcr.io/abundant-ai/ticketvector-service:main AS tv
FROM ghcr.io/abundant-ai/figma-service:latest

# Linear/Jira CLIs + their package, from the ticketvector image.
COPY --from=tv /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=tv /opt/ticketvector /opt/ticketvector

RUN pip install --no-cache-dir pytest pyyaml
COPY codebase /app
RUN ln -sf "$(command -v python3)" /usr/local/bin/python && \
    chmod +x /usr/local/bin/linear /usr/local/bin/jira

WORKDIR /app
ENV FIGMA_API_URL=http://figma:3000 \
    FIGMA_TOKEN=figma-clone-token \
    FIGMA_FILE_KEY=PrcCardHandoffFile001x \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_ACTOR=agent \
    PLANE_BASE_URL=http://ticketvector:8765 \
    PYTHONPATH=/opt:/opt/ticketvector
# Reset the figma-service serve-the-API entrypoint; `main` is just the agent box.
ENTRYPOINT []
CMD ["sleep", "infinity"]
