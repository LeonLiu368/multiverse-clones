#!/bin/sh
# Seed gh's real config dir from the delivered token so the agent sees a normal,
# logged-in gh (~/.config/gh/hosts.json) rather than any orchestration artifact.
# The token is also read directly as a fallback (see config.resolve). Backgrounded
# so the container comes up immediately; gh works once the token lands.
TOK=/run/secrets/token
CFG="${HOME:-/root}/.config/gh"
(
  i=0
  while [ ! -s "$TOK" ] && [ "$i" -lt 120 ]; do sleep 1; i=$((i+1)); done
  [ -s "$TOK" ] || exit 0
  mkdir -p "$CFG"
  printf '{"%s":{"token":"%s","user":"acme"}}\n' "${GH_HOST:-http://10.88.0.2}" "$(cat "$TOK")" > "$CFG/hosts.json"
) &
exec tail -f /dev/null
