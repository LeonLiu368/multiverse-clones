# Slack-clone service image (the `slack` service). Vendored package; self-contained.
FROM python:3.12-slim

COPY slackclone /opt/slackclone
RUN pip install --no-cache-dir /opt/slackclone

COPY slack/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /srv
ENV SLACK_DB=/srv/slack.db
ENV PORT=3000
EXPOSE 3000

# Seeds /srv/slack.db from /data/slack (slack.db | workspace.json | export/) then serves.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
