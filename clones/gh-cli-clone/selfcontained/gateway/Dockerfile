# ghc-service (base) — the gateway image: a self-hosted Forgejo forge + the
# gh-compatible CLI/MCP thin clients + the unified seeding entrypoint. NO DATA.
#
# This is the canon base of the image trio:
#   ghc-service          (this file)            — Forgejo + tools, data-free
#   ghc-service:empty     == ghc-service        — boots empty; per-task fixture mounted in
#   ghc-service:prod-v1   (Dockerfile.prod-v1)  — corpus DB baked in, mount-free
#
# Build:  docker build -f selfcontained/gateway/Dockerfile -t ghc-service .
#         (context = repo root, so `ghclone/` is available)
FROM python:3.11-slim
LABEL org.opencontainers.image.source=https://github.com/abundant-ai/gh-cli-clone
LABEL org.opencontainers.image.title="ghc Service"
LABEL org.opencontainers.image.description="GitHub-compatible Forgejo gateway with gh CLI + MCP and Actions runner for offline agent tasks"

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates libcap2-bin nodejs procps && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 git
RUN pip install --no-cache-dir httpx typer rich pydantic platformdirs jq

# Real Forgejo engine (T3) + host-mode job runner for Actions tasks.
COPY --from=codeberg.org/forgejo/forgejo:11 /app/gitea/gitea /usr/local/bin/forgejo
COPY --from=code.forgejo.org/forgejo/runner:6 /bin/forgejo-runner /usr/local/bin/forgejo-runner
# Bind :80 as the non-root git user, so the backend has no :3000 (Gitea) tell.
RUN setcap 'cap_net_bind_service=+ep' /usr/local/bin/forgejo

# The clone's CLI/MCP source lives ONLY on the gateway (never the agent).
COPY ghclone /opt/ghclone
ENV PYTHONPATH=/opt
RUN printf '#!/bin/sh\nexec python -m ghclone.cli.main "$@"\n' >/usr/local/bin/gh && \
    chmod +x /usr/local/bin/gh && cp /usr/local/bin/gh /usr/local/bin/ghc
RUN git config --system user.email runner@local && git config --system user.name runner

COPY selfcontained/gateway/gateway-entrypoint.sh /usr/local/bin/gateway-entrypoint.sh
COPY selfcontained/gateway/corpus-seed.sh /usr/local/bin/corpus-seed.sh
RUN chmod +x /usr/local/bin/gateway-entrypoint.sh /usr/local/bin/corpus-seed.sh

# A health probe compose can wire depends_on against.
HEALTHCHECK --interval=5s --timeout=3s --start-period=60s --retries=30 \
  CMD curl -fsS http://localhost/api/healthz >/dev/null || exit 1

# Default: empty boot. `:empty` is literally this image; `:prod-v1` overrides the
# data dir (Dockerfile.prod-v1) but keeps this same entrypoint.
CMD ["/usr/local/bin/gateway-entrypoint.sh"]
