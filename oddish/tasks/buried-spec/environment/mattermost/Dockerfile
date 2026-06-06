# Mattermost service image for the Oddish task.
#
# We REUSE the real Mattermost product (team edition 8.1.1) with embedded PostgreSQL —
# the same base APEX-SWE uses. This is the "be lazy, use existing code" core: threads,
# reactions, DMs, channels, users, the REST API v4, and the `mmctl` CLI all ship in here.
#
# Vendored + self-contained: the build context is the task's environment/ dir, and the
# entrypoint below is a purpose-built seeder (multi-channel, string authors, no git-time
# filtering) adapted from APEX's docker-entrypoint-mattermost-lightweight.sh.
FROM mattermost/mattermost-team-edition:8.1.1

USER root

# Embedded Postgres + python toolchain for the seeder. Baked at build time so container
# start needs no network for dependencies.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-14 postgresql-client-14 sudo python3 python3-pip curl jq && \
    pip3 install --no-cache-dir psycopg2-binary bcrypt requests && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY mattermost/entrypoint.sh /docker-entrypoint.sh
COPY mattermost/seed.py /docker-seed.py
RUN chmod +x /docker-entrypoint.sh /docker-seed.py

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
EXPOSE 8065

ENTRYPOINT ["/bin/bash", "/docker-entrypoint.sh"]
