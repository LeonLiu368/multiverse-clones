FROM python:3.13-slim

RUN apt-get update     && apt-get install -y --no-install-recommends git jq ripgrep ca-certificates     && rm -rf /var/lib/apt/lists/*

COPY shared/variant-ethereum-optimism-op-geth-770-observability/repo /app/repo
COPY shared/variant-ethereum-optimism-op-geth-770-observability/data /app/observability
WORKDIR /app/repo

RUN python -m pip install --no-cache-dir pyyaml python-dotenv parameterized
ENV PYTHONPATH=/app/repo
CMD ["sleep", "infinity"]
