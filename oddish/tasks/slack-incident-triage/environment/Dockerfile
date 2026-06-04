# Agent/client image (the `client` service in docker-compose.yaml). Self-contained:
# build context is THIS environment/ dir, which vendors the slackclone package, so the
# task uploads and builds without referencing anything outside the task directory.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

# slack-cli (the agent's tool) comes from the vendored package
COPY slackclone /opt/slackclone
RUN pip install --no-cache-dir /opt/slackclone

WORKDIR /app
ENV SLACK_API_URL=http://slack:3000
CMD ["sleep", "infinity"]
