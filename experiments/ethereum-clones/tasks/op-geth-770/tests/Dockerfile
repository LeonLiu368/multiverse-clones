FROM golang:1.25
RUN apt-get update && apt-get install -y --no-install-recommends git jq ripgrep ca-certificates python3 && rm -rf /var/lib/apt/lists/*
ENV GOTOOLCHAIN=auto
COPY . /tests
CMD ["bash", "/tests/test.sh"]
