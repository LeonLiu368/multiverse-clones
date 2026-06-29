#!/bin/sh
# Retarget the korotovsky slack-mcp-server at our in-container gateway.
#
# korotovsky builds its slack-go client against the hardcoded https://slack.com/api/ base and only
# self-retargets AFTER the first auth.test (to authResp.URL+"api/"). That first call would hit real
# Slack. This patch injects `SLACK_MCP_API_URL` (via slack-go's slack.OptionAPIURL) at BOTH startup
# client-construction sites, so every call — including the initial auth.test — goes to our gateway.
#
# The patch is a one-line insertion before each `slack.New(authProvider.SlackToken(), slackOpts...)`
# (the GOVSLACK option is appended just above, so `slackOpts`, `os`, and `slack` are already in scope).
set -e
SRC="${1:?usage: apply-patch.sh <repo-root>}"
F="$SRC/pkg/provider/api.go"
# (1) The two startup client constructions: inject SLACK_MCP_API_URL so the first auth.test (and
#     everything before the post-auth rebuild) goes to our gateway, not the hardcoded slack.com.
perl -0pi -e 's/\tslackClient := slack\.New\(authProvider\.SlackToken\(\), slackOpts\.\.\.\)/\tif u := os.Getenv("SLACK_MCP_API_URL"); u != "" {\n\t\tslackOpts = append(slackOpts, slack.OptionAPIURL(u))\n\t}\n\tslackClient := slack.New(authProvider.SlackToken(), slackOpts...)/g' "$F"
# (2) The post-auth client REBUILD uses authResp.URL+"api/". Our auth.test returns a Slack-shaped
#     URL (so korotovsky can parse the workspace name), so this rebuild would otherwise point at
#     real slack.com. Keep honoring SLACK_MCP_API_URL here too.
perl -0pi -e 's/slack\.OptionAPIURL\(authResp\.URL\+"api\/"\)/slack.OptionAPIURL(func() string { if u := os.Getenv("SLACK_MCP_API_URL"); u != "" { return u }; return authResp.URL + "api\/" }())/g' "$F"
N="$(grep -c SLACK_MCP_API_URL "$F" || true)"
[ "$N" -ge 3 ] || { echo "apply-patch: expected >=3 injections, got $N" >&2; exit 1; }
echo "apply-patch: injected SLACK_MCP_API_URL at $N sites"
