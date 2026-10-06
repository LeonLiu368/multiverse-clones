#!/usr/bin/env bash
set -euo pipefail
cd /app/src

command -v python3 >/dev/null
command -v psql >/dev/null

python3 - <<'PY'
from pathlib import Path

path = Path("catalog_repair/planner.py")
text = path.read_text()
start = text.index("def plan_repairs")
replacement = '''def plan_repairs(rows: Iterable[dict]) -> list[Repair]:
    """Return public relation backrefs whose target descriptor is absent."""
    repairs: list[Repair] = []
    for row in rows:
        if row.get("stack_key") != BACKREF_STACK_KEY:
            continue
        if row.get("descriptor_kind") != "relation":
            continue
        if row.get("relation_state") != "public":
            continue
        if bool(row.get("referenced_exists")):
            continue
        repairs.append(
            Repair(
                relation_id=int(row["relation_id"]),
                relation_name=str(row["relation_name"]),
                referenced_descriptor_id=int(row["referenced_descriptor_id"]),
                action="remove_depended_on_by_backref",
                reason="public relation has a depended-on-by back reference to a missing descriptor target",
            )
        )
    return repairs
'''
path.write_text(text[:start] + replacement)
PY

python3 tools/build_descriptor_repair.py --apply

python3 - <<'PY'
import json
import urllib.request


def rpc(method, *args, **kwargs):
    payload = json.dumps({"method": method, "args": args, "kwargs": kwargs}).encode()
    req = urllib.request.Request(
        "http://jira:8765/rpc",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    data = json.loads(urllib.request.urlopen(req, timeout=5).read().decode())
    if not data.get("ok"):
        raise RuntimeError(data)
    return data["result"]


rpc("update_issue", "CRDB-63963", state="In Review")
rpc(
    "add_comment",
    "CRDB-63963",
    "Scoped descriptor repair is ready in descriptor_backref_repair.json. Relation descriptors 193 and 211 are prepared for remove_depended_on_by_backref because their depended-on-by targets are missing; 244, 305, and 318 were left untouched because 244 resolves, 305 is dropped, and 318 is a separate forward-reference validation issue. This keeps catalog validation enabled and avoids a broad descriptor scrub.",
)
PY
