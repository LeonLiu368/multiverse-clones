# Slack-clone service image. Build context = repo root:
#   docker build -f docker/Dockerfile -t abundant-slack-clone .
FROM python:3.12-slim

WORKDIR /srv
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV SLACK_DB=/srv/slack.db
ENV PORT=3000
EXPOSE 3000

# Seeds from /data/slack (slack.db | workspace.json | export/) on first boot, then serves.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
