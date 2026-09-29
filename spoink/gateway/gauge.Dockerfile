# Bake a spoink Logfire-derived gauge state.json into a gauge-gateway image.
# Build context must contain ./state.json (the gauge Loki-log state to_gauge_state emits).
# FROM gauge-gateway:empty; the gauge-entrypoint loads GAUGE_STATE_FILE (/data/gauge/state.json),
# validates it, and serves it (gcx logs query) on :80. Analogue of the slack/jira gateway bakes.
ARG BASE=ghcr.io/abundant-ai/gauge-gateway:empty
FROM --platform=linux/amd64 ${BASE}
COPY state.json /data/gauge/state.json
