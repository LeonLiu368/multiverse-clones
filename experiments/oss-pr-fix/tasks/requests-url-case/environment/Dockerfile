FROM ghcr.io/abundant-ai/ghc-service:latest AS gh-tools
FROM ghcr.io/abundant-ai/slack-service:latest

USER root
RUN id agent >/dev/null 2>&1 || useradd --create-home --shell /bin/bash agent
COPY --from=gh-tools /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/
COPY --from=gh-tools /opt/ghclone /opt/ghclone
COPY --from=gh-tools /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.10/dist-packages
COPY wait-for-seed.sh /usr/local/bin/wait-for-seed
RUN ln -sf "$(command -v python3)" /usr/local/bin/python && \
    chmod +x /usr/local/bin/gh /usr/local/bin/ghc /usr/local/bin/wait-for-seed && \
    mkdir -p /app && \
    git config --system user.email agent@example.local && \
    git config --system user.name "Agent User" && \
    chown -R root:root /opt/ghclone && \
    chown -R agent:agent /app
WORKDIR /app
USER agent
ENV GH_HOST=http://github \
    GH_TOKEN_FILE=/run/secrets/token \
    PYTHONPATH=/opt:/opt/ghclone
CMD ["sleep", "infinity"]
