"""Build the discord-clone SQLite corpus from a real (no-admin) source OR synthetically.

Every source converges on the canonical seed dict (``schema.py``) and reuses the one
load path (``load.load_seed``), so the SQLite corpus this produces is exactly what the
gateway bakes (:prod-v1) or mounts (:empty). None of the real sources needs server
admin — adding a bot to a server is NOT required.

    python -m discordclone.seed.build_corpus --from-data-package DIR   --out discord_corpus.db
    python -m discordclone.seed.build_corpus --from-dataset FILE --map author=a content=t ts=ts channel=ch [guild=g] --out …
    python -m discordclone.seed.build_corpus --from-dce FILE [--anonymize [--strip-attachments]] --out …
    python -m discordclone.seed.build_corpus --synthetic [--guild NAME --seed N] --out …

Exactly one source flag must be given.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import importers, schema
from .load import load_seed


def build_seed(args: argparse.Namespace) -> dict[str, Any]:
    sources = [bool(args.from_data_package), bool(args.from_dataset),
               bool(args.from_dce), bool(args.synthetic)]
    if sum(sources) != 1:
        raise SystemExit("error: pass exactly one of --from-data-package / --from-dataset / "
                         "--from-dce / --synthetic")

    if args.from_data_package:
        seed = importers.from_data_package(args.from_data_package)
    elif args.from_dataset:
        mapping = importers.parse_mapping(args.map or [])
        seed = importers.from_dataset(args.from_dataset, mapping)
    elif args.from_dce:
        seed = importers.from_dce(args.from_dce)
    else:  # synthetic
        from .generator import generate
        seed = generate(guild=args.guild, seed=args.seed)

    if args.anonymize:
        seed = importers.anonymize(seed, strip_attachments=args.strip_attachments)
    return seed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="discordclone.seed.build_corpus",
                                description="Build the discord-clone corpus from a no-admin real "
                                            "source or synthetically.")
    src = p.add_argument_group("source (choose exactly one)")
    src.add_argument("--from-data-package", metavar="DIR",
                     help="Discord OFFICIAL Data Package directory (your own account; no admin)")
    src.add_argument("--from-dataset", metavar="FILE",
                     help="generic public dataset CSV/JSONL (needs --map)")
    src.add_argument("--from-dce", metavar="FILE",
                     help="DiscordChatExporter JSON (user-token or bot; no admin)")
    src.add_argument("--synthetic", action="store_true",
                     help="deterministic synthetic guild (the built-in generator)")

    p.add_argument("--map", nargs="*", default=[], metavar="KEY=COL",
                   help="dataset column mapping, e.g. author=user content=text ts=timestamp "
                        "channel=chan [guild=srv id=msg_id]")
    p.add_argument("--guild", default="Acme Engineering", help="[synthetic] guild name")
    p.add_argument("--seed", type=int, default=0, help="[synthetic] deterministic seed")

    p.add_argument("--anonymize", action="store_true",
                   help="remap real user ids/handles -> synthetic (strongly recommended for "
                        "public / user-token data)")
    p.add_argument("--strip-attachments", action="store_true",
                   help="with --anonymize: replace http(s) URLs in content with [link]")

    p.add_argument("--out", default="discord_corpus.db", help="output SQLite path")
    p.add_argument("--emit", metavar="FILE",
                   help="also write the canonical seed JSON here (for inspection/diffing)")

    args = p.parse_args(argv)
    seed = build_seed(args)

    if args.emit:
        with open(args.emit, "w", encoding="utf-8") as fh:
            fh.write(schema.to_json(schema.normalize(seed)))

    counts = load_seed(seed, args.out)
    print(json.dumps({"db": args.out, **counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
