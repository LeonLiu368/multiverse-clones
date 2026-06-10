# Agent image for variant-git-bug-git-bug-1541-observability
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git jq ripgrep ca-certificates curl python3 build-essential && rm -rf /var/lib/apt/lists/*
# ubuntu:24.04 ships an "ubuntu" user at uid 1000; replace it with "agent".
RUN userdel -r ubuntu 2>/dev/null || true; useradd --create-home --uid 1000 --shell /bin/bash agent
# System-wide Go toolchain, pinned (the repo's go.mod requires go >= 1.25.0).
RUN curl -fsSL https://go.dev/dl/go1.25.11.linux-amd64.tar.gz -o /tmp/go.tgz && \
    tar -C /usr/local -xzf /tmp/go.tgz && rm /tmp/go.tgz
ENV GOPATH=/go PATH=/usr/local/go/bin:/go/bin:$PATH GOTOOLCHAIN=auto
RUN mkdir -p /go && chmod -R 1777 /go
# Incident base snapshot: clone the upstream repo at the task's base commit
# instead of vendoring it into the task. .git/.github are removed so the agent
# sees only a clean single-commit snapshot (created below), with no upstream
# history that could leak the originating change.
RUN git clone https://github.com/git-bug/git-bug.git /app/repo && \
    git -C /app/repo checkout -q ede82f7d420ead2b9929f0d3989f6cb243d4f74b && \
    rm -rf /app/repo/.github /app/repo/.git
COPY shared/variant-git-bug-git-bug-1541-observability/ticketvector-runtime /opt/ticketvector-runtime
RUN chmod +x /opt/ticketvector-runtime/linear /opt/ticketvector-runtime/jira && \
    ln -s /opt/ticketvector-runtime/linear /usr/local/bin/linear && \
    ln -s /opt/ticketvector-runtime/jira /usr/local/bin/jira && \
    mkdir -p /var/lib/ticketvector && chown -R agent:agent /app/repo && \
    chown -R root:root /var/lib/ticketvector && chmod 700 /var/lib/ticketvector
WORKDIR /app/repo
RUN git config --global --add safe.directory /app/repo && git init -q . && git add -A && \
    git -c user.email=oncall@acme.test -c user.name=on-call commit -qm "snapshot at incident base" && \
    git gc --aggressive --prune=now -q && git config gc.auto 0 && chown -R agent:agent /app/repo
RUN go mod download >/dev/null 2>&1 || true
RUN chmod -R a+rX /go || true
ENV WORLD_ISSUES_AGENT_MODE=1 WORLD_ISSUES_BACKEND=remote WORLD_ISSUES_OUTPUT=json WORLD_ISSUES_ACTOR=agent PLANE_BASE_URL=http://ticketvector:8765
CMD ["sleep", "infinity"]
