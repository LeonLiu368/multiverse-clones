FROM gcc:14-bookworm AS builder

COPY releasectl.c /tmp/releasectl.c
RUN gcc -O2 -Wall -Wextra -o /tmp/releasectl /tmp/releasectl.c

FROM python:3.12-slim-bookworm

RUN useradd -m -s /bin/bash agent && \
    mkdir -p /app /installed-agent /var/lib/releasectl && \
    chown -R agent:agent /app /installed-agent && \
    chown root:root /var/lib/releasectl && \
    chmod 0755 /var/lib/releasectl

COPY apt-get-wrapper /usr/local/bin/apt-get
COPY curl-wrapper /usr/local/bin/curl
COPY cursor-agent-wrapper /usr/local/bin/cursor-agent
COPY sleep-wrapper /usr/local/bin/sleep
RUN chmod 0755 /usr/local/bin/apt-get /usr/local/bin/curl /usr/local/bin/cursor-agent /usr/local/bin/sleep

COPY --from=builder /tmp/releasectl /usr/local/bin/releasectl

RUN chown root:root /usr/local/bin/releasectl && \
    chmod 4511 /usr/local/bin/releasectl

WORKDIR /app
