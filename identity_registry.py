#!/usr/bin/env python3
"""Clone-agnostic PERSON IDENTITY REGISTRY generator.

One human == one named person across every clone (Slack, Jira, and future
GitHub/Sentry/... clones). Both the Slack export and the Jira backup anonymize
people with the SAME token shape ``[PERSON_NAME_<N>]``; this module turns a bare
person number ``N`` into a canonical, deterministic identity record that every
clone adopts, so the SAME ``N`` resolves to the SAME first/last name + handle
everywhere.

THE FROZEN CONSTRAINT
---------------------
The Slack prod corpus image (``slack-gateway:prod-v1``) is already built and its
synthetic names are baked into ``prod/v1/catalog/users.json``. We do NOT rebuild
it. Instead this registry REPRODUCES those existing names for the shared people,
and other clones ADOPT them.

The Slack importer assigned names with ``import_export._assign_synthetic_names``:
for a user whose raw id is ``PERSON_<N>_SLACK_ID`` it computed
``sha1("PERSON_<N>_SLACK_ID")``, indexed the FIRST/LAST name pools, then walked
the WHOLE user roster in sorted-id order assigning ``.handle`` greedily, so
collisions get numeric suffixes (``yara.kowalski`` then ``yara.kowalski2`` ...).
To reproduce a roster member's name BYTE-FOR-BYTE we must replay that exact
global sorted iteration over the exact roster the importer saw. That roster (the
141 published user ids, including non-PERSON real Slack ids and bots, which still
consume handle slots) is frozen into ``data/prod_v1_slack_roster.json``.

The name-pool + collision logic below is COPIED (not imported) from
``import_export._assign_synthetic_names`` so this registry has no runtime
dependency on the slack repo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROSTER_PATH = os.path.join(HERE, "data", "prod_v1_slack_roster.json")

# --------------------------------------------------------------------------- #
# Name pools — COPIED verbatim from abundant-slack-clone import_export.py.
# (Kept identical so the hash->name mapping matches the frozen prod-v1 image.)
# --------------------------------------------------------------------------- #
FIRST_NAMES = [
    "Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Reese",
    "Devon", "Harper", "Rowan", "Parker", "Emerson", "Skyler", "Cameron", "Drew", "Hayden", "Logan",
    "Maya", "Noah", "Priya", "Diego", "Wei", "Sofia", "Omar", "Hana", "Lucas", "Nadia",
    "Ivan", "Leila", "Kenji", "Amara", "Felix", "Yara", "Mateo", "Zoe", "Arjun", "Elena",
]
LAST_NAMES = [
    "Avila", "Brooks", "Chen", "Diaz", "Okafor", "Fischer", "Gupta", "Haddad", "Ibrahim", "Jensen",
    "Kowalski", "Lopez", "Martin", "Nakamura", "Owusu", "Petrov", "Quintero", "Reyes", "Singh", "Tan",
    "Ueda", "Vargas", "Walsh", "Xu", "Yousef", "Zhang", "Andersen", "Bianchi", "Costa", "Duval",
    "Eriksson", "Ferreira", "Goldberg", "Hassan", "Ivanov", "Johansson", "Kim", "Larsson", "Mensah", "Novak",
]

# The canonical hash key for a person number: the SAME string the Slack importer
# hashed. Keying the registry on this is what makes shared people line up.
SLACK_ID_FMT = "PERSON_{n}_SLACK_ID"

EMAIL_DOMAIN = "acme.test"

# Extract N from ANY anonymized reference a clone might hold:
#   [PERSON_NAME_14350]  PERSON_14350_SLACK_ID  PERSON_14350_JIRA_KEY  PERSON_14350_NAME ...
PERSON_REF_RE = re.compile(r"PERSON_(?:NAME_)?(\d+)")


def _name_parts(slack_key: str) -> tuple[str, str]:
    """(first, last) for a SLACK_ID hash key, matching _assign_synthetic_names."""
    h = int(hashlib.sha1(slack_key.encode()).hexdigest(), 16)
    first = FIRST_NAMES[h % len(FIRST_NAMES)]
    last = LAST_NAMES[(h // len(FIRST_NAMES)) % len(LAST_NAMES)]
    return first, last


def _handle_base(first: str, last: str, is_bot: bool) -> str:
    return f"{first.lower()}-bot" if is_bot else f"{first.lower()}.{last.lower()}"


class HandleAllocator:
    """Greedy, sorted-order handle allocation — the byte-for-byte collision replay.

    Feed it raw ids in the SAME order the Slack importer iterated (sorted) and it
    suffixes collisions exactly as ``_assign_synthetic_names`` did. ``used`` is the
    shared collision domain.
    """

    def __init__(self) -> None:
        self.used: set[str] = set()

    def take(self, base: str) -> str:
        handle, n = base, 2
        while handle in self.used:
            handle, n = f"{base}{n}", n + 1
        self.used.add(handle)
        return handle


def _load_roster() -> list[dict]:
    with open(ROSTER_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _record(n: int, first: str, last: str, handle: str, is_bot: bool, sources: list[str]) -> dict:
    """The canonical, clone-agnostic identity record for person number N."""
    real = f"{first} Bot" if is_bot else f"{first} {last}"
    display = real if is_bot else first
    return {
        "person_id": f"PERSON_NAME_{n}",
        "handle": handle,
        "display_name": display,
        "real_name": real,
        "email": f"{handle}@{EMAIL_DOMAIN}",
        "is_bot": is_bot,
        "sources": sources,
    }


def build_registry(slack_numbers: set[int], jira_numbers: set[int]) -> dict:
    """Build the registry over the UNION of person numbers from both corpora.

    Phase 1 replays the frozen prod-v1 roster (sorted-id order) so every roster
    member — including non-PERSON real Slack ids and bots that merely consume
    handle slots — reserves its handle in the shared collision domain, and the
    PERSON_<N>_SLACK_ID members get their EXACT baked name/handle.

    Phase 2 assigns the remaining union numbers (Slack-mention-only and Jira-only
    people who have no prod account), in ascending-N order, drawing from the SAME
    collision domain so we never re-mint a handle the frozen image already owns.
    """
    alloc = HandleAllocator()
    by_number: dict[int, dict] = {}

    # ---- Phase 1: replay the frozen roster in the importer's sorted-id order ----
    roster = _load_roster()
    roster_person_n: set[int] = set()
    for entry in sorted(roster, key=lambda r: r["id"]):
        rid, is_bot = entry["id"], bool(entry.get("is_bot"))
        first, last = _name_parts(rid)
        handle = alloc.take(_handle_base(first, last, is_bot))
        m = re.match(r"PERSON_(\d+)_SLACK_ID$", rid)
        if not m:
            continue  # real Slack id / UANON / bot id: reserved its handle, no person number
        n = int(m.group(1))
        roster_person_n.add(n)
        srcs = ["slack"]
        if n in jira_numbers:
            srcs.append("jira")
        by_number[n] = _record(n, first, last, handle, is_bot, srcs)

    # ---- Phase 2: everyone else in the union (no prod account) -----------------
    union = (slack_numbers | jira_numbers) - roster_person_n
    for n in sorted(union):
        first, last = _name_parts(SLACK_ID_FMT.format(n=n))
        handle = alloc.take(_handle_base(first, last, False))
        srcs = []
        if n in slack_numbers:
            srcs.append("slack")
        if n in jira_numbers:
            srcs.append("jira")
        by_number[n] = _record(n, first, last, handle, False, srcs or ["unknown"])

    return {str(n): by_number[n] for n in sorted(by_number)}


# --------------------------------------------------------------------------- #
# Consumption helpers (what a clone importer calls at seed time).
# --------------------------------------------------------------------------- #
def extract_person_number(ref: str) -> int | None:
    """Pull N from any anonymized reference, or None if not a person token."""
    if not ref:
        return None
    m = PERSON_REF_RE.search(ref)
    return int(m.group(1)) if m else None


_UNKNOWN = {
    "person_id": "PERSON_NAME_UNKNOWN", "handle": "unknown", "display_name": "Unknown",
    "real_name": "Unknown User", "email": "", "is_bot": False, "sources": [],
}


def lookup(registry: dict, ref: str) -> dict:
    """Resolve an anonymized ref to a canonical record (orphan -> unknown fallback)."""
    n = extract_person_number(ref)
    if n is None:
        return dict(_UNKNOWN)
    return registry.get(str(n), dict(_UNKNOWN))


def generate_record(n: int) -> dict:
    """Stateless single-person generator (no collision domain): the canonical name
    for N hashed on PERSON_<N>_SLACK_ID. Roster collision suffixes are only
    reproducible via build_registry; for non-colliding numbers this matches."""
    first, last = _name_parts(SLACK_ID_FMT.format(n=n))
    base = _handle_base(first, last, False)
    return _record(n, first, last, base, False, [])
