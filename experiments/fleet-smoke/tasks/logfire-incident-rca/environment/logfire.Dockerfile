# The `logfire` gateway image for this task, built self-contained from the task's
# environment/ dir so the task needs NO registry auth (compose `build:` tags it as the
# `image:` name; `up` uses the local build and never pulls). Behaviourally identical to
# the published ghcr.io/abundant-ai/logfire-service:prod-v1 — the Query API with the
# incident corpus BAKED IN (corpus/records.json.gz), served mount-free.
FROM mirror.gcr.io/library/python:3.12-slim

RUN pip install --no-cache-dir duckdb \
    && apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY logfire_clone /opt/logfire_clone
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Bake the incident corpus (prod-v1 behaviour: served as-is, mount ignored).
COPY corpus/records.json.gz /data/records.json.gz

ENV PYTHONPATH=/opt \
    LOGFIRE_RECORDS=/data/records.json \
    LOGFIRE_BAKED=/data/records.json.gz \
    LOGFIRE_PORT=80
EXPOSE 80
HEALTHCHECK --interval=5s --timeout=5s --retries=20 --start-period=20s \
  CMD curl -fsS http://localhost:80/health || exit 1
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
