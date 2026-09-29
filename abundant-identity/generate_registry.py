#!/usr/bin/env python3
"""Scan the Slack export + Jira backup, build the union registry, write registry.json.

Usage:
    python generate_registry.py \
        --slack /Users/leonliu/Downloads/slack \
        --jira  /Users/leonliu/Downloads/jira/entities.xml \
        --out   registry.json
"""
from __future__ import annotations

import argparse
import json
import os
import re

from identity_registry import build_registry

# [PERSON_NAME_<n>] is the SHARED cross-corpus token. We harvest it from both sides.
NAME_TOKEN_RE = re.compile(rb"\[PERSON_NAME_(\d+)\]")
# Jira also has an internal PERSON_<n>_JIRA_KEY/NAME/EMAIL namespace. Per the Jira
# converter's own docstring this is a DIFFERENT keyspace from the shared name token;
# we record those numbers as "jira" sources too so Jira-only account-holders are
# present, but the shared-people guarantee only spans the [PERSON_NAME_<n>] token.
JIRA_KEY_RE = re.compile(rb"PERSON_(\d+)_(?:JIRA_KEY|NAME|EMAIL)")


def scan_slack(slack_dir: str) -> set[int]:
    nums: set[int] = set()
    for root, _dirs, files in os.walk(slack_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            with open(os.path.join(root, fn), "rb") as fh:
                blob = fh.read()
            for m in NAME_TOKEN_RE.finditer(blob):
                nums.add(int(m.group(1)))
    return nums


def scan_jira(entities_path: str) -> tuple[set[int], set[int]]:
    """Return (name_token_numbers, jira_key_numbers).

    name_token_numbers are [PERSON_NAME_<n>] — the SHARED cross-corpus keyspace.
    jira_key_numbers are PERSON_<n>_JIRA_KEY/NAME/EMAIL — Jira's INTERNAL keyspace
    (a different anonymizer namespace; a JIRA_KEY <n> is NOT the same human as a
    name-token <n>, so these are not part of the shared-human overlap)."""
    name_nums: set[int] = set()
    key_nums: set[int] = set()
    with open(entities_path, "rb") as fh:
        blob = fh.read()
    for m in NAME_TOKEN_RE.finditer(blob):
        name_nums.add(int(m.group(1)))
    for m in JIRA_KEY_RE.finditer(blob):
        key_nums.add(int(m.group(1)))
    return name_nums, key_nums


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slack", default="/Users/leonliu/Downloads/slack")
    ap.add_argument("--jira", default="/Users/leonliu/Downloads/jira/entities.xml")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "registry.json"))
    args = ap.parse_args()

    slack_numbers = scan_slack(args.slack)
    jira_name_numbers, jira_key_numbers = scan_jira(args.jira)
    jira_numbers = jira_name_numbers | jira_key_numbers
    # The "same human in both corpora" overlap is the SHARED [PERSON_NAME_<n>] keyspace.
    shared_overlap = slack_numbers & jira_name_numbers

    registry = build_registry(slack_numbers, jira_numbers)

    ir = __import__("identity_registry")
    meta = {
        "_meta": {
            "schema": "abundant-identity/registry@1",
            "slack_person_numbers": len(slack_numbers),
            "jira_name_token_numbers": len(jira_name_numbers),
            "jira_internal_key_numbers": len(jira_key_numbers),
            "union_person_numbers": len(slack_numbers | jira_numbers),
            "shared_overlap_PERSON_NAME": len(shared_overlap),
            "slack_only": len(slack_numbers - jira_name_numbers),
            "jira_only_PERSON_NAME": len(jira_name_numbers - slack_numbers),
            "name_pool_first": len(ir.FIRST_NAMES),
            "name_pool_last": len(ir.LAST_NAMES),
            "hash_key_format": "PERSON_<N>_SLACK_ID",
            "shared_guarantee": "for people in the prod-v1 roster, slack.real_name == "
                                "jira.name and slack.handle == jira.handle",
        }
    }
    out = {**meta, **registry}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"wrote {args.out}")
    print(f"  slack person-numbers       : {len(slack_numbers)}")
    print(f"  jira [PERSON_NAME] numbers  : {len(jira_name_numbers)}")
    print(f"  jira internal-key numbers   : {len(jira_key_numbers)}")
    print(f"  union                       : {len(slack_numbers | jira_numbers)}")
    print(f"  shared overlap (same human) : {len(shared_overlap)}")


if __name__ == "__main__":
    main()
