# Agent image for variant-ethereum-optimism-op-geth-770-observability
FROM golang:1.25
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git jq ripgrep ca-certificates python3 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 --shell /bin/bash agent || true
ENV GOTOOLCHAIN=auto
COPY shared/variant-ethereum-optimism-op-geth-770-observability/repo /app/repo
COPY shared/variant-ethereum-optimism-op-geth-770-observability/ticketvector-runtime /opt/ticketvector-runtime
RUN chmod +x /opt/ticketvector-runtime/linear /opt/ticketvector-runtime/jira && \
    ln -s /opt/ticketvector-runtime/linear /usr/local/bin/linear && \
    ln -s /opt/ticketvector-runtime/jira /usr/local/bin/jira && \
    mkdir -p /var/lib/ticketvector && chown -R agent:agent /app/repo && \
    chown -R root:root /var/lib/ticketvector && chmod 700 /var/lib/ticketvector
WORKDIR /app/repo
RUN git config --global --add safe.directory /app/repo && git init -q . && git add -A && \
    git -c user.email=oncall@acme.test -c user.name=on-call commit -qm "snapshot at incident base" && chown -R agent:agent /app/repo
RUN go mod download >/dev/null 2>&1 || true
ENV WORLD_ISSUES_AGENT_MODE=1 WORLD_ISSUES_BACKEND=remote WORLD_ISSUES_OUTPUT=json WORLD_ISSUES_ACTOR=agent PLANE_BASE_URL=http://ticketvector:8765
CMD ["sleep", "infinity"]
