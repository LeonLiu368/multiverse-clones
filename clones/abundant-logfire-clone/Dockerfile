# Logfire clone gateway: serves POST /v2/query (SQL over `records`) on :80, backed by a baked
# records.json. Build context must contain ./records.json (rich Logfire records). Bearer read
# token (default test-token-acme-eval). Analogue of the slack/jira/gauge gateway bakes.
FROM mirror.gcr.io/library/python:3.12-slim
RUN pip install --no-cache-dir duckdb
COPY logfire_clone /opt/logfire_clone
COPY records.json /data/records.json
ENV PYTHONPATH=/opt LOGFIRE_RECORDS=/data/records.json LOGFIRE_PORT=80
EXPOSE 80
CMD ["python","-m","logfire_clone.server"]
