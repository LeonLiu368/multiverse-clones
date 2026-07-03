# One-shot provisioner image: has the docker CLI (to `docker exec` the dokku
# container), ssh-keygen, python3, git, and the baked SUT source + platform
# scripts. It provisions + deploys the SUT with the fault, then exits.
#
# Based on python:3.12-slim (already local) rather than docker:27-cli to avoid a
# registry pull. The docker CLI comes from Debian's docker.io package (client only).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client git curl openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The Debian `docker.io` package ships only the daemon, not the client. Install
# just the static docker CLI binary (client is all the provisioner needs — it
# talks to the host dockerd over the mounted socket).
ARG DOCKER_CLI_VERSION=27.3.1
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in amd64) A=x86_64;; arm64) A=aarch64;; *) A="$arch";; esac; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${A}/docker-${DOCKER_CLI_VERSION}.tgz" -o /tmp/d.tgz; \
    tar -xzf /tmp/d.tgz -C /tmp; \
    mv /tmp/docker/docker /usr/local/bin/docker; \
    rm -rf /tmp/d.tgz /tmp/docker; \
    docker --version

# platform scripts (provision-gitsync.sh) and the vendored SUT source + otel overlay
COPY platform/ /opt/platform/
COPY sut-src/ /opt/sut-src/
COPY provisioner/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /opt/platform/*.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
