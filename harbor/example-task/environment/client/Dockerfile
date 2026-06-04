# Agent/client image: has `slack-cli` pointed at the slack service, plus curl/jq/python
# for the verifier. Build context = repo root.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV SLACK_API_URL=http://slack:3000
CMD ["sleep", "infinity"]
