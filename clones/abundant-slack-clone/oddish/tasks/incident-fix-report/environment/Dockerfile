# Agent container (Harbor `main`) — built per task FROM the THIN slack-agent image.
# slack-agent carries ONLY the agent's tools (our `slack` CLI + the korotovsky `slack-mcp` server +
# pytest) on a neutral python:slim base. NO gateway (slackgw), NO importer (import_export.py), NO
# Slack data ride along — the agent reaches the workspace only over HTTP via the `slack` sidecar.
# This layer adds just the task codebase.
#
# BRANCH-ISOLATED TAG: this `slack-mcp-oss` branch builds against the branch-scoped image so it does
# NOT depend on (or clobber) the shared `:latest`. CI pushes `slack-agent:slack-mcp-oss` for this
# branch. >>> On merge to main, change this back to `:latest` (CI publishes `:latest` from main). <<<
FROM ghcr.io/abundant-ai/slack-agent-mv:latest

# The Slack workspace is the `slack` sidecar (reached by service name over HTTP), NOT localhost.
ENV SLACK_API_URL=http://slack \
    SLACK_BOT_TOKEN=xoxp-acme-eval-0001

COPY main-entrypoint.sh /usr/local/bin/main-entrypoint.sh
RUN chmod +x /usr/local/bin/main-entrypoint.sh

# The codebase the agent works on.
COPY codebase /workspace
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]
