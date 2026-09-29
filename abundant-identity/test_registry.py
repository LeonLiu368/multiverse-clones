#!/usr/bin/env python3
"""LINCHPIN TEST: the registry reproduces the frozen prod-v1 Slack names byte-for-byte.

For every user in the published prod/v1 catalog whose id is PERSON_<N>_SLACK_ID, the
registry's record for <N> must reproduce that user's real_name AND handle (name) exactly.
If this drifts, shared identities stop lining up across clones.

Also checks: collision suffixes are actually exercised (so the test is meaningful), the
generated registry.json on disk agrees with a fresh in-memory build, and ref extraction /
unknown fallback behave per the contract.
"""
import json
import os
import re

import pytest

from identity_registry import build_registry, extract_person_number, lookup

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = "/Users/leonliu/projects/abundant-slack-clone-mattermost/selfcontained/prod/v1/catalog/users.json"
REGISTRY_JSON = os.path.join(HERE, "registry.json")
SLACK_ID_RE = re.compile(r"^PERSON_(\d+)_SLACK_ID$")


def _catalog_slack_users():
    cat = json.load(open(CATALOG, encoding="utf-8"))
    out = {}
    for r in cat:
        m = SLACK_ID_RE.match(r["id"])
        if m:
            out[int(m.group(1))] = r
    return out


def _fresh_registry():
    """Build a registry whose union covers (at least) the catalog person numbers."""
    slack_nums = set(_catalog_slack_users().keys())
    return build_registry(slack_numbers=slack_nums, jira_numbers=set())


def test_catalog_has_slack_id_users():
    cat_users = _catalog_slack_users()
    assert len(cat_users) >= 60, f"expected the ~69 PERSON_N_SLACK_ID roster, got {len(cat_users)}"


def test_byte_for_byte_reproduction():
    """THE linchpin: registry record == frozen catalog name+handle, exactly."""
    cat_users = _catalog_slack_users()
    reg = _fresh_registry()
    mismatches = []
    for n, urec in cat_users.items():
        rec = reg.get(str(n))
        assert rec is not None, f"registry missing person {n}"
        if rec["real_name"] != urec["real_name"] or rec["handle"] != urec["name"]:
            mismatches.append(
                (n, urec["name"], urec["real_name"], rec["handle"], rec["real_name"])
            )
    assert not mismatches, f"{len(mismatches)} drift(s): {mismatches[:10]}"


def test_collision_suffixes_are_exercised():
    """Guards that the sorted-order collision replay actually runs — otherwise the
    byte-for-byte test could pass vacuously on a collision-free roster."""
    cat_users = _catalog_slack_users()
    suffixed = [u["name"] for u in cat_users.values() if re.search(r"\d$", u["name"])]
    assert suffixed, "expected collision-suffixed handles (e.g. elena.diaz2) in the roster"
    reg = _fresh_registry()
    for n, urec in cat_users.items():
        if re.search(r"\d$", urec["name"]):
            assert reg[str(n)]["handle"] == urec["name"], (
                f"collision handle drift for {n}: {reg[str(n)]['handle']} != {urec['name']}"
            )


def test_committed_registry_matches_catalog():
    """The committed registry.json on disk reproduces the catalog too (not just a
    fresh build) — catches a stale registry.json."""
    assert os.path.exists(REGISTRY_JSON), "registry.json not generated; run generate_registry.py"
    disk = json.load(open(REGISTRY_JSON, encoding="utf-8"))
    for n, urec in _catalog_slack_users().items():
        rec = disk.get(str(n))
        assert rec is not None, f"committed registry missing person {n}"
        assert rec["real_name"] == urec["real_name"], f"real_name drift for {n}"
        assert rec["handle"] == urec["name"], f"handle drift for {n}"


def test_shared_people_unify_slack_and_jira():
    """A person present in BOTH corpora gets ONE record with sources=[slack,jira]; the
    name is identical regardless of which corpus referenced them (the whole point)."""
    cat_users = _catalog_slack_users()
    n = next(iter(cat_users))  # any roster person
    reg = build_registry(slack_numbers={n}, jira_numbers={n})
    rec = reg[str(n)]
    assert rec["sources"] == ["slack", "jira"]
    # Same record whether a Slack mention or a Jira author references them:
    assert lookup(reg, f"[PERSON_NAME_{n}]") == rec
    assert lookup(reg, f"PERSON_{n}_JIRA_KEY") == rec
    assert lookup(reg, f"PERSON_{n}_SLACK_ID") == rec


def test_ref_extraction_and_unknown_fallback():
    assert extract_person_number("[PERSON_NAME_14350]") == 14350
    assert extract_person_number("PERSON_14350_SLACK_ID") == 14350
    assert extract_person_number("PERSON_7780_JIRA_KEY") == 7780
    assert extract_person_number("PERSON_99_NAME") == 99
    assert extract_person_number("U6W3ZPPRT") is None
    assert extract_person_number("") is None
    reg = build_registry(slack_numbers={1}, jira_numbers=set())
    fb = lookup(reg, "U6W3ZPPRT")
    assert fb["handle"] == "unknown" and fb["real_name"] == "Unknown User"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
