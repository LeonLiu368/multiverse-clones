# The `gauge` gateway sidecar for this task.
#
# Carries BOTH `build:` and `image:` in docker-compose, so Harbor's docker provider builds
# it locally and tags the pullable `ghcr.io/abundant-ai/gauge-service` name — no GHCR auth
# needed (R1.5). The `image:` name also matches the published gateway for anyone pulling.
#
# This task delivers its corpus PER TASK by mounting fixture.json into THIS container only
# (GAUGE_STATE_FILE -> the mount); the agent never sees it. (A prod/realistic variant would
# instead use `image: ghcr.io/abundant-ai/gauge-service:prod-v1` with the corpus baked in
# and no mount — switching is the image tag alone.)
FROM python:3.13-slim

ENV GAUGE_STATE_FILE=/srv/gauge/fixture.json \
    GAUGE_RUNTIME_STATE_FILE=/var/lib/gauge/state.json \
    GAUGE_ENABLE_ADMIN_API=0 \
    GAUGE_BIND_HOST=0.0.0.0 \
    GAUGE_PORT=80 \
    GRAFANA_URL=http://gauge \
    PYTHONPATH=/opt/gaugecli

WORKDIR /opt/gaugecli
COPY gauge ./gauge
COPY bin/gcx bin/mcp-grafana bin/gaugectl /usr/local/bin/
COPY entrypoint.sh /usr/local/bin/gauge-entrypoint.sh
RUN chmod +x /usr/local/bin/gcx /usr/local/bin/mcp-grafana /usr/local/bin/gaugectl /usr/local/bin/gauge-entrypoint.sh && \
    mkdir -p /srv/gauge /var/lib/gauge

EXPOSE 80
HEALTHCHECK --interval=2s --timeout=2s --retries=30 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1/api/healthz', timeout=1).read()"
ENTRYPOINT ["/usr/local/bin/gauge-entrypoint.sh"]
