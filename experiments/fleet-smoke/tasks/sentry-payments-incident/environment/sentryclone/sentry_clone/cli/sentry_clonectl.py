from __future__ import annotations

import argparse

from .client import SentryAdminClient, SentryClientError
from .output import emit_json, error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentry-clonectl", description="Sentry-clone admin/debug CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("state")
    sub.add_parser("mutations")
    args = parser.parse_args(argv)
    client = SentryAdminClient()
    try:
        if args.cmd == "state":
            emit_json(client.clone_state())
        elif args.cmd == "mutations":
            emit_json(client.clone_mutations())
    except SentryClientError as exc:
        error(str(exc))
        return getattr(exc, "exit_code", 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
