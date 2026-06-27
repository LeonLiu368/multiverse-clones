"""CLI: generate a task from a spec.json.

    python -m spoink.pipeline spec.json --out generated-tasks/

The spec is a TaskSpec serialized to JSON (see spec.py). Typically you export a skeleton from
the dashboard Task Creator, fill in the baked gateway image tags + the SUT bundle + the verifier
strategy, then run this.
"""
from __future__ import annotations

import argparse
import json

from .generate import generate_task
from .spec import load_spec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="spoink.pipeline", description="Generate a task from a spec.json")
    ap.add_argument("spec", help="path to a TaskSpec JSON")
    ap.add_argument("--out", default="generated-tasks", help="output dir (task lands at <out>/<slug>/)")
    args = ap.parse_args(argv)
    res = generate_task(load_spec(args.spec), args.out)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
