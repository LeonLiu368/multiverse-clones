FROM python:3.11-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    nodejs \
    npm \
    postgresql-client \
    wget \
  && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash agent
WORKDIR /app/src

COPY shared/tbmq-persistent-session-offset-gap/app-src/ /app/src/

RUN mkdir -p /app/artifacts \
  && chown -R agent:agent /app /app/artifacts

USER agent
