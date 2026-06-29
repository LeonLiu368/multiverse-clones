# Self-contained "world": Forgejo + ghc in ONE container. No external network, no
# compose — works in any cloud sandbox (Daytona/Modal). The forge boots + seeds via
# the task's healthcheck (scripts forge-up.sh), and `gh`/`ghc` are wired to it.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates curl procps && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir httpx typer rich pydantic platformdirs

# non-root user for Forgejo (it refuses to run as root)
RUN useradd -m -u 1000 git

# the agent-facing ghc, exposed as both `ghc` and `gh` (no hydrate/migrate here).
# The wrapper sources the seeded token from /etc/ghc/token so `gh` works for any user.
COPY ghclone /opt/ghclone
ENV PYTHONPATH=/opt
RUN printf '#!/bin/sh\n[ -f /etc/ghc/token ] && export GHC_TOKEN="$(cat /etc/ghc/token)"\nexec python -m ghclone.cli.main "$@"\n' > /usr/local/bin/ghc \
 && chmod +x /usr/local/bin/ghc && cp /usr/local/bin/ghc /usr/local/bin/gh

# multi-arch Forgejo binary lifted from the official image (resolves to build arch)
COPY --from=codeberg.org/forgejo/forgejo:11 /app/gitea/gitea /usr/local/bin/forgejo

COPY forge-up.sh /usr/local/bin/forge-up.sh
RUN chmod +x /usr/local/bin/forge-up.sh

ENV GHC_HOST=http://localhost:3300
RUN git config --system user.email agent@local && git config --system user.name agent
WORKDIR /app
