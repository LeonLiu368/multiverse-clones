FROM gcc:14-bookworm AS builder

COPY arrayctl.c /tmp/arrayctl.c
RUN gcc -O2 -Wall -Wextra -o /tmp/arrayctl /tmp/arrayctl.c -lm

FROM python:3.12-slim-bookworm

RUN useradd -m -s /bin/bash agent && \
    mkdir -p /app /installed-agent /var/lib/arrayctl && \
    chown -R agent:agent /app /installed-agent && \
    chown root:root /var/lib/arrayctl && \
    chmod 0755 /var/lib/arrayctl

COPY apt-get-wrapper /usr/local/bin/apt-get
COPY curl-wrapper /usr/local/bin/curl
COPY cursor-agent-wrapper /usr/local/bin/cursor-agent
COPY sleep-wrapper /usr/local/bin/sleep
RUN chmod 0755 /usr/local/bin/apt-get /usr/local/bin/curl /usr/local/bin/cursor-agent /usr/local/bin/sleep

COPY --from=builder /tmp/arrayctl /usr/local/bin/arrayctl

RUN chown root:root /usr/local/bin/arrayctl && \
    chmod 4511 /usr/local/bin/arrayctl

WORKDIR /app
