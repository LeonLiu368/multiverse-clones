# logfire-service (BASE) — the data-free gateway image: the Logfire Query API
# (POST /v2/query, SQL over `records`) backed by DuckDB. Carries NO corpus. This is
# the canon base from which `:empty` and `:prod-v1` derive. A corpus arrives either
# baked (prod-v1) or mounted at $LOGFIRE_RECORDS (empty).
FROM mirror.gcr.io/library/python:3.12-slim

RUN pip install --no-cache-dir duckdb \
    && apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY logfire_clone /opt/logfire_clone
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PYTHONPATH=/opt \
    LOGFIRE_RECORDS=/data/records.json \
    LOGFIRE_BAKED=/data/records.json.gz \
    LOGFIRE_PORT=80
EXPOSE 80
HEALTHCHECK --interval=5s --timeout=5s --retries=20 --start-period=20s \
  CMD curl -fsS http://localhost:80/health || exit 1
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
