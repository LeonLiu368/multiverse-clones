FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update     && apt-get install -y --no-install-recommends git jq ripgrep ca-certificates python3 python3-pip     && rm -rf /var/lib/apt/lists/*
# ubuntu:24.04 ships an "ubuntu" user at uid 1000; replace it with "agent".
RUN userdel -r ubuntu 2>/dev/null || true; useradd --create-home --uid 1000 --shell /bin/bash agent

# Incident base snapshot: clone the upstream repo at the task's base commit
# instead of vendoring it. .git/.github (and a few unrelated example/integration
# fixtures) are removed to match the slimmed incident snapshot.
RUN git clone https://github.com/containers/podman-compose.git /app/repo && \
    git -C /app/repo checkout -q 1a86aeba3ea94c6a723c7deae2fa146b9c5f8b7d && \
    rm -rf /app/repo/.git /app/repo/.github \
           /app/repo/examples/nodeproj/.home /app/repo/examples/nodeproj/lib \
           /app/repo/tests/integration/build /app/repo/tests/integration/interpolation/.env
COPY shared/variant-containers-podman-compose-1296-observability/data/loki /app/observability/loki
COPY shared/variant-containers-podman-compose-1296-observability/data/mattermost /app/observability/mattermost
COPY shared/variant-containers-podman-compose-1296-observability/ticketvector-runtime /opt/ticketvector-runtime
RUN chmod +x /opt/ticketvector-runtime/linear /opt/ticketvector-runtime/jira && \
    ln -s /opt/ticketvector-runtime/linear /usr/local/bin/linear && \
    ln -s /opt/ticketvector-runtime/jira /usr/local/bin/jira && \
    mkdir -p /var/lib/ticketvector && \
    chown -R agent:agent /app/repo /app/observability && \
    chown -R root:root /var/lib/ticketvector && \
    chmod 700 /var/lib/ticketvector
WORKDIR /app/repo
# Re-init the slimmed checkout as a single-commit snapshot so the agent can
# commit its fix and the verifier can resolve commit evidence against it.
RUN git config --global --add safe.directory /app/repo && git init -q . && git add -A && \
    git -c user.email=oncall@acme.test -c user.name=on-call commit -qm "snapshot at incident base" && chown -R agent:agent /app/repo

RUN python3 -m pip install --no-cache-dir --break-system-packages pyyaml==6.0.2 python-dotenv==1.0.1 parameterized==0.9.0
ENV PYTHONPATH=/app/repo
ENV WORLD_ISSUES_AGENT_MODE=1 \
    WORLD_ISSUES_BACKEND=remote \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_ACTOR=agent \
    PLANE_BASE_URL=http://ticketvector:8765
CMD ["sleep", "infinity"]
