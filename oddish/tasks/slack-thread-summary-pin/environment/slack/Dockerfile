# Slack-clone SERVICE image. Self-contained: build context is the task's
# environment/ dir (see docker-compose.yaml), which vendors the package and this
# task's single workspace seed — so the task builds inside Harbor's sandbox with no
# reference outside the task directory.
#
# The seed (workspace.json) is COPYed ONLY into THIS service image; it is never
# copied into the agent image and the task source is not mounted into the agent, so
# the agent cannot read the answer key — it must use the tools.
FROM python:3.12-slim

COPY slackclone /opt/slackclone
RUN pip install --no-cache-dir /opt/slackclone

COPY slack/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY slack/workspace.json /srv/workspace.json

ENV SLACK_DB=/srv/slack.db
ENV PORT=3000
EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
