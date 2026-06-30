from __future__ import annotations

import argparse
import sys

from .client import GrafanaAdminClient, GrafanaClientError
from .output import emit_json, error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grafanactl", description="Grafana admin/debug CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("state")
    sub.add_parser("mutations")
    args = parser.parse_args(argv)
    client = GrafanaAdminClient()
    try:
        if args.cmd == "state":
            emit_json(client.clone_state())
        elif args.cmd == "mutations":
            emit_json(client.clone_mutations())
    except GrafanaClientError as exc:
        error(str(exc))
        return getattr(exc, "exit_code", 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
