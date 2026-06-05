# Slack-clone SERVICE image (the `slack` container). Build context = repo root:
#   docker build -f docker/Dockerfile -t abundant-slack-clone:latest .
FROM python:3.12-slim

WORKDIR /srv
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Bake the canonical workspace catalog into the image. A task picks one by name
# (SLACK_WORKSPACE=<name>); the seed data therefore never lives in a task dir.
COPY workspaces /srv/workspaces

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV SLACK_DB=/srv/slack.db
ENV SLACK_WORKSPACE_DIR=/srv/workspaces
ENV SLACK_WORKSPACE=""
ENV PORT=3000
EXPOSE 3000

# On first boot: seed by name from the baked catalog (SLACK_WORKSPACE), else fall
# back to a mounted /data/slack source, else synthetic. Then serve. See entrypoint.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
