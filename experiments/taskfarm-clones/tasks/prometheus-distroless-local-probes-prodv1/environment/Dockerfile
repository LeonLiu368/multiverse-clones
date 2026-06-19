ARG GHC_SERVICE_IMAGE=ghcr.io/abundant-ai/ghc-service:latest@sha256:d4e88d7fa4af0ae84213d54f4b884b3a8954ebad9fe88b6f6fb97cea1443b3cf
ARG TICKETVECTOR_SERVICE_IMAGE=ghcr.io/abundant-ai/ticketvector-service:main@sha256:9a3feabe3d493adec7c678d6e89b92fd3b65ac05cc788fae97b4fcf674fb4f42
FROM ${GHC_SERVICE_IMAGE} AS gh-tools
FROM ${TICKETVECTOR_SERVICE_IMAGE} AS ticketvector-tools
FROM rancher/k3s:v1.31.5-k3s1 AS k8s-tools
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client git curl ca-certificates && rm -rf /var/lib/apt/lists/* && useradd --create-home --shell /bin/bash agent
COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/
COPY --from=gh-tools /opt/ghclone /opt/ghclone
COPY --from=gh-tools /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=ticketvector-tools /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/
COPY --from=ticketvector-tools /opt/ticketvector /opt/ticketvector
COPY --from=k8s-tools /bin/kubectl /usr/local/bin/kubectl
COPY bin/gcx bin/mcp-grafana /usr/local/bin/
COPY shared/prometheus-distroless-local-probes/app-src /app/src
RUN chmod +x /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/linear /usr/local/bin/jira /usr/local/bin/kubectl /usr/local/bin/gcx /usr/local/bin/mcp-grafana 2>/dev/null || true
RUN mkdir -p /app/artifacts /var/lib/ticketvector && git -C /app/src init && git -C /app/src config user.email agent@example.local && git -C /app/src config user.name 'Agent User' && git -C /app/src add . && GIT_AUTHOR_DATE='2026-05-31T18:00:00Z' GIT_COMMITTER_DATE='2026-05-31T18:00:00Z' git -C /app/src commit -m 'Initial distroless probe incident snapshot' && chown -R agent:agent /app/src /app/artifacts
WORKDIR /app/src
USER agent
ENV PGHOST=postgres PGUSER=agent PGDATABASE=acme_prometheus_distroless_local_probes GH_HOST=http://github GH_TOKEN_FILE=/run/secrets/token PLANE_BASE_URL=http://jira:8765 WORLD_ISSUES_BACKEND=remote WORLD_ISSUES_AGENT_MODE=1 WORLD_ISSUES_OUTPUT=json WORLD_ISSUES_ACTOR=agent WORLD_ISSUES_DEFAULT_PROJECT=PROMOP PLANE_API_KEY=test-token-acme-eval GRAFANA_URL=http://gcx:3000 GRAFANA_BASIC_AUTH=admin:admin KUBECONFIG=/tmp/kubeconfig PYTHONPATH=/app/src:/opt:/opt/ghclone:/opt/ticketvector:${PYTHONPATH}
CMD ["sleep", "infinity"]
