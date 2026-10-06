#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from pathlib import Path

from prometheus_operator.probe_policy import is_distroless, render_probe


ARTIFACT = Path("/app/artifacts/prometheus_distroless_probe_repair.json")
EXPECTED = ["prom-ceems-primary", "prom-edge-rules"]
UNTOUCHED = ["prom-legacy-shell", "prom-public-metrics"]


def load_instances():
    data = json.loads(Path("ops/prometheus_instances.yaml").read_text())
    return data["instances"]


def probe_kind(probe):
    if "exec" in probe:
        return "exec"
    if "httpGet" in probe:
        return "httpGet"
    return "unknown"


def build_plan(instances):
    affected = []
    untouched = []
    for instance in instances:
        rendered = render_probe(instance, "readiness")
        after_kind = probe_kind(rendered)
        before_kind = instance["current_probe_kind"]
        is_target = bool(instance.get("listenLocal")) and is_distroless(instance) and before_kind == "exec"
        if is_target and after_kind == "httpGet":
            affected.append(
                {
                    "instance_id": instance["instance_id"],
                    "namespace": instance["namespace"],
                    "before_kind": before_kind,
                    "after_kind": after_kind,
                    "probe_path": rendered["httpGet"].get("path"),
                    "evidence": [instance["evidence"]],
                }
            )
        else:
            untouched.append(instance["instance_id"])
    return {
        "ticket_id": "PROMOP-8605",
        "incident_id": "distroless-listenlocal-probes",
        "affected_instances": affected,
        "untouched_instances": sorted(set(untouched)),
        "broad_workaround_rejected": "Kept the repair in the renderer instead of rolling back all distroless images or changing every Prometheus probe.",
        "scope_note": "Only distroless listenLocal instances that previously rendered exec probes are switched.",
    }


def psql(sql):
    env = os.environ.copy()
    subprocess.check_call(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql], env=env)


def apply_database(plan):
    ids = sorted(item["instance_id"] for item in plan["affected_instances"])
    for item in plan["affected_instances"]:
        instance_id = item["instance_id"].replace("'", "''")
        psql(
            "update probe_inventory "
            "set current_probe_kind='httpGet', repair_action='switch-to-httpget' "
            f"where instance_id='{instance_id}'"
        )
        psql(
            "insert into repair_audit(record_id, action, artifact, note) values "
            f"('{instance_id}', 'switch-to-httpget', '{ARTIFACT}', 'distroless listenLocal exec probe repaired')"
        )
    repaired = ",".join(ids).replace("'", "''")
    psql(
        "update incident_status "
        f"set status='recovered', repaired_ids='{repaired}', artifact='{ARTIFACT}' "
        "where ticket='PROMOP-8605'"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = build_plan(load_instances())
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    if args.apply:
        apply_database(plan)
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
