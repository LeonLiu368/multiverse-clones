ARG GHC_SERVICE_IMAGE=ghcr.io/abundant-ai/ghc-service:latest@sha256:d4e88d7fa4af0ae84213d54f4b884b3a8954ebad9fe88b6f6fb97cea1443b3cf
ARG TICKETVECTOR_SERVICE_IMAGE=ghcr.io/abundant-ai/ticketvector-service:main@sha256:9a3feabe3d493adec7c678d6e89b92fd3b65ac05cc788fae97b4fcf674fb4f42
FROM ${GHC_SERVICE_IMAGE} AS gh-tools
FROM ${TICKETVECTOR_SERVICE_IMAGE} AS ticketvector-tools
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client git curl ca-certificates jq bash && rm -rf /var/lib/apt/lists/* && useradd --create-home --shell /bin/bash agent
COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/
COPY --from=gh-tools /opt/ghclone /opt/ghclone
COPY --from=gh-tools /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=ticketvector-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=ticketvector-tools /opt/ticketvector /opt/ticketvector
COPY bin/gcx bin/mcp-grafana /usr/local/bin/
COPY shared/tpcc-lockservice-memory-pressure/app-src /app/src
RUN chmod +x /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/gcx /usr/local/bin/mcp-grafana 2>/dev/null || true
RUN mkdir -p /app/artifacts /var/lib/ticketvector && git -C /app/src init && git -C /app/src config user.email agent@example.local && git -C /app/src config user.name 'Agent User' && git -C /app/src add . && GIT_AUTHOR_DATE='2026-06-16T09:30:00Z' GIT_COMMITTER_DATE='2026-06-16T09:30:00Z' git -C /app/src commit -m 'Initial MatrixOne TPCC incident snapshot' && chown -R agent:agent /app/src /app/artifacts
WORKDIR /app/src
USER agent
ENV PGHOST=postgres PGUSER=agent PGDATABASE=matrixone_tpcc_lockservice GH_HOST=http://github GH_TOKEN_FILE=/run/secrets/token PLANE_BASE_URL=http://jira:8765 WORLD_ISSUES_BACKEND=remote WORLD_ISSUES_AGENT_MODE=1 WORLD_ISSUES_OUTPUT=json WORLD_ISSUES_ACTOR=agent WORLD_ISSUES_DEFAULT_PROJECT=MO PLANE_API_KEY=test-token-acme-eval GRAFANA_URL=http://gcx:3000 GRAFANA_BASIC_AUTH=admin:admin PYTHONPATH=/app/src:/opt:/opt/ghclone:/opt/ticketvector:${PYTHONPATH}
CMD ["sleep", "infinity"]
