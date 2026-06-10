FROM python:3.13
RUN apt-get update && apt-get install -y --no-install-recommends git jq ripgrep ca-certificates build-essential curl libpoppler-cpp-dev poppler-utils ghostscript imagemagick optipng unpaper tesseract-ocr libmagic1 libzbar0 pkg-config && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.19
RUN mkdir -p /app /var/lib/ticketvector
COPY . /tests
CMD ["bash", "/tests/test.sh"]
