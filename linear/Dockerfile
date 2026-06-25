# Linear GraphQL gateway: serves api.linear.app/graphql-shape over the SAME state.json the
# jira-gateway bakes, so a real linear-mcp / Linear GraphQL client works. Sidecar alongside
# jira-gateway (Plane-RPC + linear CLI) over the same corpus. Build context needs ./state.json.
FROM mirror.gcr.io/library/python:3.12-slim
RUN pip install --no-cache-dir "graphql-core>=3.2"
COPY linear /opt/linear
COPY state.json /var/lib/ticketvector/state.json
ENV PYTHONPATH=/opt LINEAR_STATE=/var/lib/ticketvector/state.json LINEAR_PORT=80
EXPOSE 80
CMD ["python","-m","linear.server"]
