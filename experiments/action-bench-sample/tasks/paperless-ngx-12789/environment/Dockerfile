# Agent image for variant-paperless-ngx-paperless-ngx-12789-observability
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git jq ripgrep ca-certificates build-essential curl python3 libpoppler-cpp-dev poppler-utils ghostscript imagemagick optipng unpaper tesseract-ocr libmagic1 libzbar0 pkg-config && rm -rf /var/lib/apt/lists/*
# ubuntu:24.04 ships an "ubuntu" user at uid 1000; replace it with "agent".
RUN userdel -r ubuntu 2>/dev/null || true; useradd --create-home --uid 1000 --shell /bin/bash agent
# uv (pinned); `uv sync` below provisions the project's managed Python 3.13.
RUN curl -LsSf https://github.com/astral-sh/uv/releases/download/0.11.19/uv-x86_64-unknown-linux-gnu.tar.gz | tar -xz -C /usr/local/bin --strip-components=1
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
# Incident base snapshot: clone the upstream repo at the task's base commit
# instead of vendoring it. .git/.github/docs/src-ui are removed to match the
# slimmed incident snapshot (the task touches the Django backend under src/).
RUN git clone https://github.com/paperless-ngx/paperless-ngx.git /app/repo && \
    git -C /app/repo checkout -q 5f42854d9999d8c455656447e28c8c0916e28e37 && \
    rm -rf /app/repo/.git /app/repo/.github /app/repo/docs /app/repo/src-ui
COPY shared/variant-paperless-ngx-paperless-ngx-12789-observability/ticketvector-runtime /opt/ticketvector-runtime
RUN chmod +x /opt/ticketvector-runtime/linear /opt/ticketvector-runtime/jira && \
    ln -s /opt/ticketvector-runtime/linear /usr/local/bin/linear && \
    ln -s /opt/ticketvector-runtime/jira /usr/local/bin/jira && \
    mkdir -p /var/lib/ticketvector && chown -R agent:agent /app/repo && \
    chown -R root:root /var/lib/ticketvector && chmod 700 /var/lib/ticketvector
WORKDIR /app/repo
RUN git config --global --add safe.directory /app/repo && git init -q . && git add -A && \
    git -c user.email=oncall@acme.test -c user.name=on-call commit -qm "snapshot at incident base" && chown -R agent:agent /app/repo
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN cd /app/repo && (uv sync --all-groups || uv sync --frozen --all-extras || uv sync) >/dev/null 2>&1 || true
RUN chmod -R a+rX /opt/venv /opt/uv-python 2>/dev/null || true
ENV WORLD_ISSUES_AGENT_MODE=1 WORLD_ISSUES_BACKEND=remote WORLD_ISSUES_OUTPUT=json WORLD_ISSUES_ACTOR=agent PLANE_BASE_URL=http://ticketvector:8765
CMD ["sleep", "infinity"]
