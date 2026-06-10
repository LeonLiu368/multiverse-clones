#!/usr/bin/env python3
import argparse
import json

from payments.replay import DEFAULT_ARTIFACT, DEFAULT_FIXTURE, write_replay


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the payment retry incident fixture.")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--out", default=str(DEFAULT_ARTIFACT))
    args = parser.parse_args()
    summary = write_replay(args.out, args.fixture)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
