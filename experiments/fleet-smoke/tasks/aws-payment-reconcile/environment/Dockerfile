# Agent (`main`) container — Harbor builds this automatically as the agent's image.
# It ships ONLY the agent's tools: the real `aws`/`awslocal` CLI (which talk to the
# `aws` gateway over AWS_ENDPOINT_URL) and the `aws-mcp` MCP server. No corpus, no
# state.json, no seed generator: the agent reaches AWS state solely through the
# tools, pointed at the `aws` service.
#
# Leak hygiene (R2.k / R6.3): we copy ONLY the agent-safe slice of aws_clone (the
# mcp/ server + the cli/client.py admin HTTP client). aws_clone/seed (the seed
# generator) and aws_clone/admin (the gateway server) are NOT copied, so
# `import aws_clone.seed` raises and the planted answer is neither greppable nor
# regenerable on the agent box. A build-time smoke test asserts this.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --target /opt/awscli \
      awscli==1.31.13 \
      boto3==1.33.13 \
      botocore==1.33.13 \
      awscli-local==0.22.0 && \
    python -m pip install --no-cache-dir "mcp>=1.0" && \
    mkdir -p /opt/aws-clone/aws_clone/mcp /opt/aws-clone/aws_clone/cli

# CLI + MCP launchers.
COPY bin/aws bin/awslocal bin/aws-mcp /usr/local/bin/
RUN chmod +x /usr/local/bin/aws /usr/local/bin/awslocal /usr/local/bin/aws-mcp

# Agent-safe slice of aws_clone only.
COPY aws_clone/__init__.py /opt/aws-clone/aws_clone/__init__.py
COPY aws_clone/mcp /opt/aws-clone/aws_clone/mcp
COPY aws_clone/cli/__init__.py /opt/aws-clone/aws_clone/cli/__init__.py
COPY aws_clone/cli/client.py /opt/aws-clone/aws_clone/cli/client.py
RUN find /opt/aws-clone -name '__pycache__' -type d -prune -exec rm -rf {} + && \
    PYTHONPATH=/opt/aws-clone:/opt/awscli python -c "import aws_clone.mcp.server, aws_clone.mcp.tools" && \
    aws --version >/dev/null 2>&1 || true && \
    ! PYTHONPATH=/opt/aws-clone:/opt/awscli python -c "import aws_clone.seed" 2>/dev/null && \
    test ! -e /opt/aws-clone/aws_clone/seed && \
    test ! -e /opt/aws-clone/aws_clone/admin && \
    ! grep -rsq 'pay-20260630-batch7' /opt /usr/local/lib/python*/site-packages 2>/dev/null && \
    echo "thin agent OK (no seed/, no admin/; no answer leak; aws + aws-mcp load)"

ENV PYTHONPATH=/opt/aws-clone:/opt/awscli \
    AWS_ENDPOINT_URL=http://aws:4566 \
    AWS_ACCESS_KEY_ID=test \
    AWS_SECRET_ACCESS_KEY=test \
    AWS_DEFAULT_REGION=us-east-1
WORKDIR /workspace
CMD ["sleep", "infinity"]
