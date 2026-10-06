#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from catalog_repair.planner import plan_repairs


ARTIFACT = Path("/app/artifacts/descriptor_backref_repair.json")
UNTOUCHED_DECOYS = [244, 305, 318]


def ensure_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"required tool missing from PATH: {name}")


def psql(args: list[str], input_text: str | None = None) -> str:
    ensure_tool("psql")
    base = [
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-h",
        os.environ.get("PGHOST", "postgres"),
        "-U",
        os.environ.get("PGUSER", "agent"),
        "-d",
        os.environ.get("PGDATABASE", "crdb_descriptor_backref_repair"),
    ]
    result = subprocess.run(base + args, input=input_text, text=True, check=True, stdout=subprocess.PIPE)
    return result.stdout


def load_rows() -> list[dict]:
    sql = """
SELECT relation_id, relation_name, descriptor_kind, relation_state, referenced_descriptor_id,
       referenced_exists, stack_key
FROM descriptor_backrefs
ORDER BY relation_id;
"""
    out = psql(["-At", "-F", "\t", "-c", sql])
    rows: list[dict] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        relation_id, relation_name, descriptor_kind, relation_state, ref_id, ref_exists, stack_key = line.split("\t")
        rows.append(
            {
                "relation_id": int(relation_id),
                "relation_name": relation_name,
                "descriptor_kind": descriptor_kind,
                "relation_state": relation_state,
                "referenced_descriptor_id": int(ref_id),
                "referenced_exists": ref_exists == "t",
                "stack_key": stack_key,
            }
        )
    return rows


def build_artifact(rows: list[dict]) -> dict:
    repairs = plan_repairs(rows)
    return {
        "ticket": "CRDB-63963",
        "sentry_event": "evt-crdb-170371",
        "artifact_version": 1,
        "affected_descriptor_ids": [repair.relation_id for repair in repairs],
        "repairs": [
            {
                "relation_id": repair.relation_id,
                "relation_name": repair.relation_name,
                "referenced_descriptor_id": repair.referenced_descriptor_id,
                "action": repair.action,
                "reason": repair.reason,
            }
            for repair in repairs
        ],
        "untouched_descriptor_ids": UNTOUCHED_DECOYS,
        "broad_workaround_rejected": "catalog validation stays enabled; only missing-target depended-on-by backrefs on public relation descriptors are prepared for removal",
    }


def apply_repairs(artifact: dict) -> None:
    ids = [int(value) for value in artifact["affected_descriptor_ids"]]
    if not ids:
        raise SystemExit("no affected descriptors selected")
    values = ",".join(f"({relation_id})" for relation_id in ids)
    sql = f"""
WITH selected(relation_id) AS (VALUES {values})
UPDATE descriptor_backrefs d
SET repair_action = 'remove_depended_on_by_backref',
    repair_status = 'ready',
    repair_note = 'prepared by descriptor_backref_repair.json'
FROM selected
WHERE d.relation_id = selected.relation_id;

WITH selected(relation_id) AS (VALUES {values})
INSERT INTO descriptor_repair_audit (relation_id, action, artifact_path)
SELECT relation_id, 'remove_depended_on_by_backref', '/app/artifacts/descriptor_backref_repair.json'
FROM selected
ON CONFLICT DO NOTHING;

UPDATE descriptor_incidents
SET status = 'repair_ready', updated_at = now()
WHERE ticket_id = 'CRDB-63963';
"""
    psql(["-q", "-c", sql])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="update Postgres repair state after writing the artifact")
    args = parser.parse_args()
    rows = load_rows()
    artifact = build_artifact(rows)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    if args.apply:
        apply_repairs(artifact)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
