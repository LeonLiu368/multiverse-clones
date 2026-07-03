# OTel-instrumented wrapper for the vendored RealWorld "Conduit" FastAPI app
# (live/sut-conduit/app, provenance in live/MANIFEST.json). Overlaid at the root
# of the deploy repo by platform/provision.sh, replacing the upstream
# poetry-based Dockerfile (kept in the vendored tree for provenance only).
#
# Zero app-code changes: OpenTelemetry auto-instrumentation via
# `opentelemetry-instrument` (fastapi/asgi/asyncpg instrumentors from
# requirements.txt). All OTel config arrives as runtime env via dokku config:set:
#   OTEL_SERVICE_NAME=conduit
#   OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
#   OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
#   OTEL_TRACES_EXPORTER=otlp  OTEL_METRICS_EXPORTER=otlp  OTEL_LOGS_EXPORTER=otlp
# or OTEL_SDK_DISABLED=true to run without a collector (smoke-test mode).
#
# App runtime env (via dokku config:set):
#   DATABASE_URL=postgresql://user:pass@host:5432/db   (postgresql:// scheme —
#     SQLAlchemy 1.4 alembic rejects the legacy postgres:// alias)
#   SECRET_KEY=<jwt secret>
#   WEB_CONCURRENCY  <- the P4 fault knob: uvicorn worker-process count, read
#     natively by uvicorn (no code/CMD change). Faulty = 1 (bcrypt logins block
#     the single event loop under load; healthy at rest), fix = 4.
#   MAX_CONNECTIONS_COUNT / MIN_CONNECTIONS_COUNT  <- app-native asyncpg pool
#     bounds (keep 10/5). Measured NOT to degrade on this stack — see
#     otel-wrap/README.md for the numbers; WEB_CONCURRENCY is the proven knob.

FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    # only the http/protobuf OTLP exporter is installed; make it the default so
    # OTEL_TRACES_EXPORTER=otlp works without also setting the protocol var
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

WORKDIR /app

# gcc: asyncpg 0.26.0 ships no aarch64 cp39 wheel, so pip compiles it.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 8000

# Migrations at boot (idempotent, retried until the DB answers — a dokku deploy
# may race postgres startup), then the auto-instrumented server. Worker count
# comes from WEB_CONCURRENCY (uvicorn reads it natively when --workers is not
# passed) — that env var is the P4 fault knob (faulty=1, fix=4).
CMD until alembic upgrade head; do echo "[boot] waiting for database..."; sleep 2; done && \
    exec opentelemetry-instrument uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
