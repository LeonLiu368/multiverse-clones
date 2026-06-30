# The `sentry` gateway image for this task, built self-contained from the vendored
# sentryclone/ tree (the clone's HTTP API + sentry/sentry-mcp/sentry-clonectl thin
# clients + the boot entrypoint), with NO task data baked in. Built locally by
# `docker compose build`; compose tags it as the published image name so the task
# needs no registry auth (R1.5 build:+image: dual). Behaviorally identical to the
# published ghcr.io/abundant-ai/sentry-clone-service:empty — per-task design data is
# MOUNTED at /data/sentry-clone/state.json (this service container only).
FROM python:3.13-slim

ENV SENTRY_CLONE_STATE_FILE=/data/sentry-clone/state.json \
    SENTRY_CLONE_RUNTIME_STATE_FILE=/var/lib/sentry-clone/state.json \
    SENTRY_CLONE_CORPUS_FILE=/srv/sentry-clone/corpus-state.json \
    SENTRY_CLONE_BIND_HOST=0.0.0.0 \
    SENTRY_CLONE_PORT=80 \
    PYTHONPATH=/opt/sentry-clone-cli

WORKDIR /opt/sentry-clone-cli
COPY sentryclone/sentry_clone ./sentry_clone
COPY sentryclone/bin/sentry sentryclone/bin/sentry-mcp sentryclone/bin/sentry-clonectl /usr/local/bin/
COPY sentryclone/entrypoint.sh /usr/local/bin/sentry-clone-entrypoint.sh
RUN chmod +x /usr/local/bin/sentry /usr/local/bin/sentry-mcp /usr/local/bin/sentry-clonectl /usr/local/bin/sentry-clone-entrypoint.sh && \
    mkdir -p /data/sentry-clone /var/lib/sentry-clone

EXPOSE 80
HEALTHCHECK --interval=2s --timeout=2s --retries=30 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1/api/healthz', timeout=1).read()"
ENTRYPOINT ["/usr/local/bin/sentry-clone-entrypoint.sh"]
