#!/usr/bin/env bash
# Build the base agent image `ghc-agent:local` that Harbor sample tasks FROM.
# Bakes ghclone (exposed as `gh` + `ghc`, AGENT SURFACE ONLY — no hydrate) and
# points GHC_HOST/GHC_TOKEN at the local forge. The token stays local to the
# image; sample task Dockerfiles just `FROM ghc-agent:local` so they're committable.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
GHC_HOST="${GHC_HOST:-http://host.docker.internal:3300}"
GHC_TOKEN="${GHC_TOKEN:-$(cat "$HERE/ghc-token.txt" 2>/dev/null)}"

CTX="$(mktemp -d)"
cp -r "$HERE/ghclone" "$CTX/ghclone"
cat > "$CTX/Dockerfile" <<DOCKER
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir httpx typer rich pydantic platformdirs
COPY ghclone /opt/ghclone
ENV PYTHONPATH=/opt
# Expose ONLY the agent-facing CLI as gh + ghc (cli.main has no hydrate/migrate).
RUN printf '#!/bin/sh\nexec python -m ghclone.cli.main "\$@"\n' > /usr/local/bin/ghc && chmod +x /usr/local/bin/ghc \
 && cp /usr/local/bin/ghc /usr/local/bin/gh
ENV GHC_HOST=$GHC_HOST
ENV GHC_TOKEN=$GHC_TOKEN
RUN git config --system user.email agent@local && git config --system user.name agent
WORKDIR /app
DOCKER
docker build -q -t ghc-agent:local "$CTX" >/dev/null
rm -rf "$CTX"
echo "built ghc-agent:local (GHC_HOST=$GHC_HOST)"
