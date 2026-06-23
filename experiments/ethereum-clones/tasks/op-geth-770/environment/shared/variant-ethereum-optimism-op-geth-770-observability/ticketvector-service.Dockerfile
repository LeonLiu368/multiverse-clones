FROM python:3.13-slim

ENV WORLD_ISSUES_BACKEND=fake \
    WORLD_ISSUES_OUTPUT=json \
    WORLD_ISSUES_ACTOR=agent \
    WORLD_ISSUES_STATE_FILE=/var/lib/ticketvector/state.json \
    WORLD_ISSUES_BIND_HOST=0.0.0.0 \
    WORLD_ISSUES_PORT=8765

WORKDIR /opt/ticketvector-runtime
COPY ticketvector-runtime /opt/ticketvector-runtime
RUN chmod +x /opt/ticketvector-runtime/linear /opt/ticketvector-runtime/jira && \
    mkdir -p /var/lib/ticketvector

EXPOSE 8765
HEALTHCHECK --interval=2s --timeout=2s --retries=30 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=1).read()"
CMD ["python", "-m", "world_issues.server"]
