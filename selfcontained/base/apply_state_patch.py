#!/usr/bin/env python3
"""apply_state_patch.py — stdlib-only boot-time mutator for a ticketvector state.json.

Two modes (exactly one of --overlay / --patch):

  --overlay <file>   ADDITIVE MERGE of a full or partial state.json into --state.
                     issues:  concatenated; identifiers already present in the base
                              are KEPT (base wins) — the overlay ADDS new issues.
                     users/states/labels/cycles/modules: union by id (then name/handle).
                     comments/links/relations/history/attachments: merged by issue
                              identifier (overlay lists appended to base lists).
                     Prints  OVERLAY_OK issues+=N

  --patch <file>     op-list mutation of --state. Format:
                     {"version":1,"ops":[ {op,entity,match,set}, ... ]}
                     op    ∈ add|update|delete
                     entity∈ issue|comment|user|state
                       issue:   add (set=full fields) | update | delete
                       comment: add (match issue) | delete (match issue, set.comment_id)
                       user:    add
                       state:   add
                     Fails LOUD (SystemExit "PATCH_ERROR …") if a match resolves to
                     0 rows, so a stale/typo'd key aborts boot instead of silently
                     no-op'ing. Prints  PATCH_OK ops=N

The state is mutated in place on disk (rewritten to --state).
"""
import argparse
import json
import sys
from datetime import datetime, timezone


def die(msg: str) -> "None":
    raise SystemExit(msg)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        die(f"PATCH_ERROR file not found: {path}")
    except json.JSONDecodeError as exc:
        die(f"PATCH_ERROR invalid json in {path}: {exc}")


def save(path: str, state: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# OVERLAY (additive merge)
# ---------------------------------------------------------------------------
def _id_keys(item: dict) -> tuple:
    """Identity tuple used to de-dup union'd collections (users/states/etc.)."""
    return (
        item.get("id"),
        item.get("name"),
        item.get("handle"),
    )


def _union_by_identity(base: list, extra: list) -> int:
    """Append items from `extra` not already present in `base` (by id/name/handle).
    Returns the number of items added."""
    seen = set()
    for it in base:
        if isinstance(it, dict):
            seen.update(k for k in _id_keys(it) if k)
    added = 0
    for it in extra or []:
        keys = {k for k in _id_keys(it) if k} if isinstance(it, dict) else {it}
        if keys & seen:
            continue
        base.append(it)
        seen.update(keys)
        added += 1
    return added


def _merge_keyed_lists(base: dict, extra: dict) -> None:
    """For dicts keyed by issue identifier -> list, append overlay lists to base."""
    for key, items in (extra or {}).items():
        base.setdefault(key, [])
        base[key].extend(items)


def normalize_state(state: dict) -> int:
    """Coerce the per-identifier keyed collections to dicts, the shape the server's write paths
    require (FakePlaneBackend.update_issue does `self.history.setdefault(...)` etc.). The prod
    corpus bakes `history` as an empty LIST `[]` (a converter quirk), which is fine for read-only
    tasks but raises AttributeError on the first write. Coerce `[] -> {}`; a populated list keyed
    by issue identifier is regrouped into a dict. Returns the number of fields fixed."""
    fixed = 0
    for coll in ("comments", "links", "relations", "history", "attachments"):
        val = state.get(coll)
        if isinstance(val, dict) or val is None:
            continue
        if isinstance(val, list):
            regrouped: dict = {}
            for item in val:
                ident = (item.get("issue") or item.get("identifier")) if isinstance(item, dict) else None
                if ident:
                    regrouped.setdefault(ident, []).append(item)
            state[coll] = regrouped  # [] -> {}, populated list -> grouped by issue identifier
            fixed += 1
    return fixed


def apply_overlay(state: dict, overlay: dict) -> int:
    # issues: ADD ones whose identifier is not already present; base wins on collision.
    existing = {i.get("identifier") for i in state.get("issues", [])}
    added_issues = 0
    state.setdefault("issues", [])
    for issue in overlay.get("issues", []) or []:
        ident = issue.get("identifier")
        if ident in existing:
            continue
        state["issues"].append(issue)
        existing.add(ident)
        added_issues += 1

    # union scalar reference collections by identity
    for coll in ("users", "states", "labels", "cycles", "modules"):
        if overlay.get(coll):
            state.setdefault(coll, [])
            _union_by_identity(state[coll], overlay[coll])

    # merge per-identifier keyed dicts
    for coll in ("comments", "links", "relations", "history", "attachments"):
        if overlay.get(coll):
            state.setdefault(coll, {})
            _merge_keyed_lists(state[coll], overlay[coll])

    return added_issues


# ---------------------------------------------------------------------------
# PATCH (op-list)
# ---------------------------------------------------------------------------
def _find_issue(state: dict, key: str) -> dict:
    for issue in state.get("issues", []):
        if issue.get("identifier", "").lower() == key.lower() or issue.get("id") == key:
            return issue
    die(f"PATCH_ERROR issue match resolved 0 rows: {key}")


def _resolve_state(state: dict, value: str) -> dict:
    """Mirror FakePlaneBackend._state(): match a states[] entry by id, name, or category."""
    for st in state.get("states", []):
        if (
            st.get("id") == value
            or st.get("name", "").lower() == str(value).lower()
            or st.get("category") == value
        ):
            return {k: st[k] for k in st}
    die(f"PATCH_ERROR state not found: {value}")


def _resolve_user(state: dict, handle: str) -> dict:
    for u in state.get("users", []):
        if (
            u.get("handle") == handle
            or u.get("id") == handle
            or u.get("name", "").lower() == str(handle).lower()
        ):
            return {k: u[k] for k in u}
    die(f"PATCH_ERROR user not found: {handle}")


def _resolve_labels(state: dict, names: list) -> list:
    wanted = set(names)
    out = [dict(l) for l in state.get("labels", []) if l.get("name") in wanted]
    missing = wanted - {l.get("name") for l in out}
    if missing:
        die(f"PATCH_ERROR label(s) not found: {sorted(missing)}")
    return out


def _next_identifier(state: dict) -> str:
    key = (state.get("project") or {}).get("key", "ISSUE")
    nums = [
        int(i["identifier"].rsplit("-", 1)[1])
        for i in state.get("issues", [])
        if i.get("identifier", "").startswith(key + "-") and i["identifier"].rsplit("-", 1)[1].isdigit()
    ]
    return f"{key}-{(max(nums) + 1) if nums else 1}"


def _op_add_issue(state: dict, fields: dict) -> None:
    ident = fields.get("identifier") or _next_identifier(state)
    if any(i.get("identifier") == ident for i in state.get("issues", [])):
        die(f"PATCH_ERROR issue already exists: {ident}")
    states = state.get("states", [])
    issue = {
        "id": f"issue-{ident.lower()}",
        "identifier": ident,
        "project": dict(state.get("project", {})),
        "title": fields.get("title", ""),
        "description": fields.get("description", ""),
        "state": _resolve_state(state, fields["state"]) if fields.get("state") else dict(states[0]) if states else {},
        "priority": fields.get("priority", "medium"),
        "assignees": [_resolve_user(state, h) for h in fields.get("assignees", [])],
        "labels": _resolve_labels(state, fields.get("labels", [])),
        "cycle": None,
        "module": None,
        "links": [],
        "relations": [],
        "comments_count": 0,
        "attachments_count": 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    state.setdefault("issues", []).append(issue)


def _op_delete_comment(state: dict, match: dict, fields: dict) -> None:
    ident = _find_issue(state, match["key"])["identifier"]
    cid = fields.get("comment_id")
    bucket = state.get("comments", {}).get(ident, [])
    kept = [c for c in bucket if c.get("id") != cid]
    if len(kept) == len(bucket):
        die(f"PATCH_ERROR comment match resolved 0 rows: {cid}")
    state["comments"][ident] = kept
    issue = _find_issue(state, ident)
    if "comments_count" in issue:
        issue["comments_count"] = len(kept)


def _op_update_issue(state: dict, match: dict, fields: dict) -> None:
    issue = _find_issue(state, match["key"])
    if "title" in fields and fields["title"]:
        issue["title"] = fields["title"]
    if "description" in fields and fields["description"] is not None:
        issue["description"] = fields["description"]
    if "priority" in fields and fields["priority"]:
        issue["priority"] = fields["priority"]
    if "state" in fields and fields["state"]:
        # map a state NAME (or id/category) to the matching states[] object
        issue["state"] = _resolve_state(state, fields["state"])
    if "assignees" in fields:
        issue["assignees"] = [_resolve_user(state, h) for h in fields["assignees"]]
    if "labels" in fields:
        issue["labels"] = _resolve_labels(state, fields["labels"])
    if "updated_at" in issue:
        issue["updated_at"] = now_iso()


def _op_delete_issue(state: dict, match: dict) -> None:
    issue = _find_issue(state, match["key"])
    ident = issue["identifier"]
    state["issues"] = [i for i in state["issues"] if i.get("identifier") != ident]
    for coll in ("comments", "links", "relations", "history", "attachments"):
        if coll in state and isinstance(state[coll], dict):
            state[coll].pop(ident, None)


def _op_add_comment(state: dict, match: dict, fields: dict) -> None:
    issue = _find_issue(state, match["key"])
    ident = issue["identifier"]
    state.setdefault("comments", {})
    bucket = state["comments"].setdefault(ident, [])
    author_handle = fields.get("author", "agent")
    author = _resolve_user(state, author_handle)
    comment = {
        "id": f"comment-{ident.lower()}-overlay-{len(bucket) + 1}",
        "issue": ident,
        "author": author,
        "body": fields.get("body", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    bucket.append(comment)
    # keep the denormalized counter in sync if the issue carries one
    if "comments_count" in issue:
        issue["comments_count"] = len(bucket)


def _op_add_user(state: dict, fields: dict) -> None:
    state.setdefault("users", [])
    handle = fields["handle"]
    if any(u.get("handle") == handle for u in state["users"]):
        die(f"PATCH_ERROR user already exists: {handle}")
    state["users"].append(
        {
            "id": fields.get("id", f"user-{handle}"),
            "handle": handle,
            "name": fields.get("name", handle),
        }
    )


def _op_add_state(state: dict, fields: dict) -> None:
    state.setdefault("states", [])
    name = fields["name"]
    if any(s.get("name") == name for s in state["states"]):
        die(f"PATCH_ERROR state already exists: {name}")
    entry = {
        "id": fields.get("id", f"state-{name.lower().replace(' ', '-')}"),
        "name": name,
    }
    if "category" in fields:
        entry["category"] = fields["category"]
    state["states"].append(entry)


def apply_patch(state: dict, patch: dict) -> int:
    ops = patch.get("ops")
    if not isinstance(ops, list):
        die("PATCH_ERROR patch has no 'ops' list")
    for idx, op in enumerate(ops):
        kind = op.get("op")
        entity = op.get("entity")
        match = op.get("match") or {}
        fields = op.get("set") or {}
        if entity == "issue" and kind == "add":
            _op_add_issue(state, fields)
        elif entity == "issue" and kind == "update":
            _op_update_issue(state, match, fields)
        elif entity == "issue" and kind == "delete":
            _op_delete_issue(state, match)
        elif entity == "comment" and kind == "add":
            _op_add_comment(state, match, fields)
        elif entity == "comment" and kind == "delete":
            _op_delete_comment(state, match, fields)
        elif entity == "user" and kind == "add":
            _op_add_user(state, fields)
        elif entity == "state" and kind == "add":
            _op_add_state(state, fields)
        else:
            die(f"PATCH_ERROR unsupported op[{idx}]: op={kind!r} entity={entity!r}")
    return len(ops)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--overlay")
    grp.add_argument("--patch")
    grp.add_argument("--normalize", action="store_true",
                     help="only coerce keyed collections to the server's write-faithful dict shape")
    args = ap.parse_args(argv)

    state = load(args.state)
    # Always normalize first so writes (update_issue/add_comment) work against any corpus shape.
    nfix = normalize_state(state)

    if args.overlay:
        overlay = load(args.overlay)
        added = apply_overlay(state, overlay)
        save(args.state, state)
        print(f"OVERLAY_OK issues+={added} normalized={nfix}")
    elif args.patch:
        patch = load(args.patch)
        n = apply_patch(state, patch)
        save(args.state, state)
        print(f"PATCH_OK ops={n} normalized={nfix}")
    else:
        save(args.state, state)
        print(f"NORMALIZE_OK normalized={nfix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
