# Reproduce the figma-service image trio from a clean checkout.
#
#   make images   -> builds figma-service, :empty, and :prod-v1 locally
#   make corpus   -> regenerates the deterministic figma_corpus.db
#
# CI (.github/workflows/figma-service-image.yml) builds + pushes the same three
# tags multi-arch (linux/amd64,linux/arm64). The base + :empty are identical in
# behavior; :prod-v1 bakes the corpus DB and boots mount-free.
IMAGE ?= ghcr.io/abundant-ai/figma-service
PY ?= python3

.PHONY: images base empty prod-v1 corpus clean-corpus

corpus: figma_corpus.db

figma_corpus.db:
	$(PY) scripts/build_corpus.py --out figma_corpus.db

base:
	docker build -f docker/Dockerfile -t $(IMAGE):latest .

empty:
	docker build -f docker/Dockerfile.empty -t $(IMAGE):empty .

prod-v1: empty figma_corpus.db
	docker build -f docker/Dockerfile.prod-v1 \
		--build-arg BASE=$(IMAGE):empty \
		-t $(IMAGE):prod-v1 .

images: base empty prod-v1
	@echo "built: $(IMAGE):latest  $(IMAGE):empty  $(IMAGE):prod-v1"

clean-corpus:
	rm -f figma_corpus.db
