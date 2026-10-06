#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from pathlib import Path

from pkg.sql.catalog.tabledesc.validate_partitioning import classify_descriptor_case


ARTIFACT = Path("/app/artifacts/cockroach_partition_tuple_guard_plan.json")
TICKET = "CRDB-63642"


def psql(sql):
    return subprocess.check_output(
        ["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
        text=True,
        env=os.environ.copy(),
    ).strip()


def rows():
    payload = psql(
        """
        select coalesce(json_agg(row_to_json(t)), '[]'::json)
        from (
          select case_id, ticket, partition_tuple_hex, tuple_arity::text,
                 observed_error, guard_state, expected_action
          from descriptor_validation_cases
          order by case_id
        ) t
        """
    )
    return json.loads(payload)


def build_plan():
    actions = []
    untouched = []
    for row in rows():
        action = classify_descriptor_case(row)
        if action:
            actions.append(action)
        elif row["case_id"] in {
            "tenant_77_geo_archive_intentional_empty",
            "tenant_18_inventory_hash_shard",
            "tenant_65_customers_expr_index",
        }:
            untouched.append(row["case_id"])
    return {
        "ticket": TICKET,
        "actions": actions,
        "untouched": sorted(untouched),
        "rationale": "Use a narrow scoped guard only for CRDB-63642 malformed empty tuple payloads with nonzero arity; do not skip all partition validation or rewrite every descriptor.",
    }


def apply_plan(plan):
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    for action in plan["actions"]:
        psql(
            """
            insert into repair_audit(record_id, ticket, action, artifact)
            values (%(record_id)s, 'CRDB-63642', 'guard_empty_tuple_decode', '/app/artifacts/cockroach_partition_tuple_guard_plan.json')
            on conflict (record_id) do nothing
            """.replace("%(record_id)s", "'" + action["id"].replace("'", "''") + "'")
        )
    repaired = ",".join(sorted(action["id"] for action in plan["actions"]))
    psql(
        """
        update incident_status
        set status='recovered', repaired_ids='%(repaired)s', artifact='/app/artifacts/cockroach_partition_tuple_guard_plan.json'
        where ticket='CRDB-63642'
        """.replace("%(repaired)s", repaired.replace("'", "''"))
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = build_plan()
    if args.apply:
        apply_plan(plan)
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
