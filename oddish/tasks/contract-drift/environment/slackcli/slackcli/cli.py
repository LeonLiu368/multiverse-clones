"""The `slack` CLI — the agent's command-line Slack tool.

Usage:
  slack whoami
  slack channels
  slack history <channel> [--limit N]
  slack search "<query>"
  slack users
  slack post <channel> "<text>"

Add --json to any command for raw JSON (otherwise prints a compact human view). Configured via
$SLACK_API_URL and $SLACK_BOT_TOKEN (preset in the environment).
"""
from __future__ import annotations

import argparse
import json
import sys

from . import client


def _emit(obj, as_json: bool, human):
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    else:
        human(obj)


def _fmt_channels(chans):
    for c in chans:
        topic = (c.get("topic") or {}).get("value") if isinstance(c.get("topic"), dict) else c.get("topic")
        print(f"{c.get('id'):<12} #{c.get('name','')}  {topic or ''}".rstrip())


def _fmt_messages(msgs):
    for m in msgs:
        print(f"[{m.get('ts','')}] {m.get('user','')}: {m.get('text','')}")


def _fmt_users(users):
    for u in users:
        print(f"{u.get('id'):<12} {u.get('name','')}  {u.get('real_name','')}".rstrip())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="slack", description="Slack Web API command-line tool")
    p.add_argument("--json", action="store_true", help="output raw JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="show the authenticated identity")
    sub.add_parser("channels", help="list channels")
    sub.add_parser("users", help="list users")

    h = sub.add_parser("history", help="read a channel's recent messages")
    h.add_argument("channel", help="channel name (e.g. general) or id (C…)")
    h.add_argument("--limit", type=int, default=50)

    s = sub.add_parser("search", help="full-text message search (noisy — read carefully)")
    s.add_argument("query")

    po = sub.add_parser("post", help="post a message to a channel")
    po.add_argument("channel")
    po.add_argument("text")

    args = p.parse_args(argv)
    try:
        if args.cmd == "whoami":
            _emit(client.whoami(), args.json, lambda d: print(d.get("user"), d.get("team")))
        elif args.cmd == "channels":
            _emit(client.list_channels(), args.json, _fmt_channels)
        elif args.cmd == "users":
            _emit(client.list_users(), args.json, _fmt_users)
        elif args.cmd == "history":
            _emit(client.history(args.channel, args.limit), args.json, _fmt_messages)
        elif args.cmd == "search":
            _emit(client.search(args.query), args.json, _fmt_messages)
        elif args.cmd == "post":
            _emit(client.post_message(args.channel, args.text), args.json,
                  lambda d: print(f"posted to {d.get('channel')} @ {d.get('ts')}"))
    except Exception as e:  # surface gateway/SDK errors cleanly
        print(f"slack: error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
