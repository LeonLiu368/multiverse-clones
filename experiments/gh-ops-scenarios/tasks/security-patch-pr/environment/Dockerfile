FROM ghcr.io/abundant-ai/ghc-service@sha256:d4e88d7fa4af0ae84213d54f4b884b3a8954ebad9fe88b6f6fb97cea1443b3cf AS gh-tools

FROM python:3.11-slim

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git curl ca-certificates jq bash && rm -rf /var/lib/apt/lists/*

# Copy the gh wrapper script and ghclone Python package from the service image.
COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/gh
COPY --from=gh-tools /usr/local/bin/ghc /usr/local/bin/ghc
COPY --from=gh-tools /opt/ghclone /opt/ghclone

# Install the ghclone Python dependencies.
RUN pip install --no-cache-dir httpx typer rich pydantic platformdirs jq

# Wire gh: point at the github sidecar; token auto-read from /run/secrets/token.
ENV PYTHONPATH=/opt \
    GH_HOST=http://github

RUN git config --system user.email agent@local && git config --system user.name agent

WORKDIR /app
CMD ["sleep", "infinity"]
