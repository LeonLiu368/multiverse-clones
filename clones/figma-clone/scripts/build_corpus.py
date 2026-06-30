#!/usr/bin/env python3
"""Deterministically build the ``figma_corpus.db`` baked into ``figma-service:prod-v1``.

A clean checkout runs this to reproduce the prod corpus from source — no out-of-band
file dump required. The corpus is several deterministic design-system files under one
team/project, generated from fixed seeds, so the same checkout always emits a
byte-stable DB (R1.6). The result is served as-is by ``:prod-v1`` with no fixture mount
(R2.j): ``COPY figma_corpus.db /srv/figma.db``.

Usage:
    python scripts/build_corpus.py [--out figma_corpus.db]

If you have a REAL ``GET /v1/files/:key`` dump and want to bake that instead, use
``figma-cli seed import-file <dump.json> --out figma_corpus.db`` — same DB shape.
"""

from __future__ import annotations

import argparse
import os
import sys

# allow running from a checkout without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from figmaclone.seed.generator import generate  # noqa: E402
from figmaclone.seed.load import load_seed_into_engine  # noqa: E402
from figmaclone.db import get_engine, init_db  # noqa: E402

# (file_name, seed) — fixed so the corpus is reproducible. Each is a full
# design-system file with components, styles, comments and version history.
CORPUS_FILES = [
    ("Acme Design System", 42),
    ("Marketing Site", 7),
    ("Mobile App Kit", 1337),
    ("Dashboard Components", 2024),
]


def build(out: str) -> dict:
    engine = get_engine(out)
    init_db(engine)
    total = {"files": 0, "projects": 0, "comments": 0, "versions": 0}
    # one shared team/project across the corpus so team/project listings are rich
    for name, seed in CORPUS_FILES:
        sd = generate(file_name=name, seed=seed)
        # fold every file under one canonical team T1 / project P1
        sd["team"] = {"id": "T1", "name": "Acme Design"}
        sd["projects"] = [{"id": "P1", "name": "Product Design",
                           "files": [f["key"] for f in sd["files"]]}]
        counts = load_seed_into_engine(sd, engine)
        for k in total:
            total[k] += counts.get(k, 0)
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="figma_corpus.db", help="output SQLite path")
    args = ap.parse_args()
    if os.path.exists(args.out):
        os.remove(args.out)
    counts = build(args.out)
    print(f"built {args.out}: {counts}")


if __name__ == "__main__":
    main()
