ARG GHC_SERVICE_IMAGE=ghcr.io/abundant-ai/ghc-service:latest@sha256:d4e88d7fa4af0ae84213d54f4b884b3a8954ebad9fe88b6f6fb97cea1443b3cf
ARG TICKETVECTOR_SERVICE_IMAGE=ghcr.io/abundant-ai/ticketvector-service:main@sha256:9a3feabe3d493adec7c678d6e89b92fd3b65ac05cc788fae97b4fcf674fb4f42
ARG SENTRY_SERVICE_IMAGE=ghcr.io/abundant-ai/sentry-clone-service:main
FROM ${GHC_SERVICE_IMAGE} AS gh-tools
FROM ${TICKETVECTOR_SERVICE_IMAGE} AS ticketvector-tools
FROM ${SENTRY_SERVICE_IMAGE} AS sentry-tools
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client git curl ca-certificates && rm -rf /var/lib/apt/lists/* && useradd --create-home --shell /bin/bash agent
COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/
COPY --from=gh-tools /opt/ghclone /opt/ghclone
COPY --from=gh-tools /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=ticketvector-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=ticketvector-tools /opt/ticketvector /opt/ticketvector
COPY --from=sentry-tools /usr/local/bin/sentry /usr/local/bin/sentry-mcp /usr/local/bin/
COPY --from=sentry-tools /opt/sentry-clone-cli /opt/sentry-clone-cli
COPY shared/cockroach-partition-tuple-guard/app-src /app/src
RUN chmod +x /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/sentry /usr/local/bin/sentry-mcp 2>/dev/null || true
RUN mkdir -p /app/artifacts /var/lib/ticketvector && git -C /app/src init && git -C /app/src config user.email agent@example.local && git -C /app/src config user.name 'Agent User' && git -C /app/src add . && GIT_AUTHOR_DATE='2026-05-21T15:04:00Z' GIT_COMMITTER_DATE='2026-05-21T15:04:00Z' git -C /app/src commit -m 'Initial CRDB-63642 task snapshot' && chown -R agent:agent /app/src /app/artifacts
WORKDIR /app/src
USER agent
ENV PGHOST=postgres PGUSER=agent PGDATABASE=acme_cockroach_partition_tuple_guard GH_HOST=http://github GH_TOKEN_FILE=/run/secrets/token PLANE_BASE_URL=http://jira:8765 WORLD_ISSUES_BACKEND=remote WORLD_ISSUES_AGENT_MODE=1 WORLD_ISSUES_OUTPUT=json WORLD_ISSUES_ACTOR=agent WORLD_ISSUES_DEFAULT_PROJECT=CRDB PLANE_API_KEY=test-token-acme-eval SENTRY_URL=http://sentry SENTRY_AUTH_TOKEN=test-token-acme-eval SENTRY_ORG=acme PYTHONPATH=/app/src:/opt:/opt/ghclone:/opt/ticketvector:/opt/sentry-clone-cli:${PYTHONPATH}
CMD ["sleep", "infinity"]
