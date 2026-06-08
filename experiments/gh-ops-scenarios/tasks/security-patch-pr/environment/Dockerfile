# ghc-service is the runtime base: Python 3.11 + gh/ghc/ghclone already baked in, lives on
# GHCR so there are no Docker Hub pull-rate-limit issues.
FROM ghcr.io/abundant-ai/ghc-service@sha256:d4e88d7fa4af0ae84213d54f4b884b3a8954ebad9fe88b6f6fb97cea1443b3cf

# jq is the only tool not already present in the base image (git/curl/bash/pip3 are there).
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    jq && rm -rf /var/lib/apt/lists/*

# gh/ghc/ghclone are already in the base — no COPY needed.

# Install the ghclone Python dependencies.
RUN pip install --no-cache-dir httpx typer rich pydantic platformdirs jq

# Wire gh: point at the github sidecar; token auto-read from /run/secrets/token.
ENV PYTHONPATH=/opt \
    GH_HOST=http://github

RUN git config --system user.email agent@local && git config --system user.name agent

WORKDIR /app
CMD ["sleep", "infinity"]
