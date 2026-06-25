# Bake a spoink-captured issue corpus into a jira-gateway image (deployed family).
#
# Build context must contain ./state.json = the ticketvector state.json that
# spoink.linear_export emits. FROM jira-gateway:empty, which carries the
# jira-boot.sh entrypoint: at boot it builds a writable runtime copy and runs
# apply_state_patch.py --normalize (history/comments []->{}) so the baked corpus
# is write-safe, then serves it on :8765. Analogue of slack-gateway baking.
ARG BASE=ghcr.io/abundant-ai/jira-gateway:empty
ARG PROJECT=
FROM --platform=linux/amd64 ${BASE}
COPY state.json /var/lib/ticketvector/state.json
ENV WORLD_ISSUES_DEFAULT_PROJECT=${PROJECT}
