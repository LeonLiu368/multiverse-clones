FROM python:3.13-slim

RUN apt-get update     && apt-get install -y --no-install-recommends git jq ripgrep ca-certificates     && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir pyyaml==6.0.2 python-dotenv==1.0.1 parameterized==0.9.0
RUN mkdir -p /app /var/lib/ticketvector
COPY . /tests
ENV PYTHONPATH=/app/repo
CMD ["bash", "/tests/test.sh"]
