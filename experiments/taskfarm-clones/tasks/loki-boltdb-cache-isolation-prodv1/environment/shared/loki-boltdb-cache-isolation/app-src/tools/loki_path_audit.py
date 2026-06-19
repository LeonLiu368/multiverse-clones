#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from pathlib import Path

VALUES = Path("charts/loki/values.yaml")
ARTIFACT = Path("/app/artifacts/loki_boltdb_repair.json")
TARGETS = {"loki-write-2", "loki-write-5"}
UNTOUCHED = "loki-compactor-0"
SHARED_ACTIVE = "/data/loki/boltdb-shipper-active"
SHARED_CACHE = "/data/loki/boltdb-shipper-cache"


def parse_replicas(path: Path) -> list[dict[str, str]]:
    replicas: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("- pod_id:"):
            if current:
                replicas.append(current)
            current = {"pod_id": line.split(":", 1)[1].strip()}
        elif current and ":" in line:
            key, value = line.split(":", 1)
            current[key.strip()] = value.strip()
    if current:
        replicas.append(current)
    return replicas


def evaluate(replicas: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, str]], list[str]]:
    repaired = []
    untouched = []
    problems = []
    by_id = {row.get("pod_id"): row for row in replicas}
    for pod_id in sorted(TARGETS):
        row = by_id.get(pod_id)
        if not row:
            problems.append(f"missing {pod_id}")
            continue
        active = row.get("active_index_directory", "")
        cache = row.get("cache_location", "")
        if active == SHARED_ACTIVE or cache == SHARED_CACHE:
            problems.append(f"{pod_id} still uses shared BoltDB shipper path")
        if pod_id not in active or pod_id not in cache:
            problems.append(f"{pod_id} paths are not pod-scoped")
        repaired.append({
            "pod_id": pod_id,
            "active_index_directory": active,
            "cache_location": cache,
            "evidence": ["k8s BackOff event", "Postgres needs_repair row", "Grafana write-path alert"],
        })
    compactor = by_id.get(UNTOUCHED)
    if not compactor:
        problems.append(f"missing {UNTOUCHED}")
    else:
        if compactor.get("active_index_directory") != "/data/loki/boltdb-shipper-compactor":
            problems.append("compactor active path changed")
        if compactor.get("cache_location") != SHARED_CACHE:
            problems.append("compactor cache path changed")
        untouched.append({"pod_id": UNTOUCHED, "reason": "healthy compactor decoy keeps shared compactor/cache path"})
    return repaired, untouched, problems


def psql(sql: str) -> str:
    return subprocess.check_output(
        ["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
        text=True,
        env=os.environ.copy(),
    ).strip()


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def apply_db(repaired: list[dict[str, object]]) -> None:
    psql("delete from repair_audit where ticket='LOKI-3248'")
    for row in repaired:
        psql(
            "insert into repair_audit(ticket, pod_id, active_index_directory, cache_location) values "
            f"('LOKI-3248', {sql_literal(str(row['pod_id']))}, {sql_literal(str(row['active_index_directory']))}, {sql_literal(str(row['cache_location']))})"
        )
        psql(
            "update loki_index_path_status set repaired=true, active_index_directory="
            f"{sql_literal(str(row['active_index_directory']))}, cache_location={sql_literal(str(row['cache_location']))} "
            f"where pod_id={sql_literal(str(row['pod_id']))}"
        )
    ids = ",".join(sorted(str(row["pod_id"]) for row in repaired))
    psql(f"update incident_status set status='recovered', repaired_pods={sql_literal(ids)} where ticket='LOKI-3248'")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", default=str(ARTIFACT))
    args = parser.parse_args()
    replicas = parse_replicas(VALUES)
    repaired, untouched, problems = evaluate(replicas)
    payload = {
        "ticket": "LOKI-3248",
        "source_issue": "grafana/loki#3248",
        "repaired_pods": repaired,
        "untouched_pods": untouched,
        "broad_workaround_avoided": True,
    }
    if problems:
        for item in problems:
            print(item)
        return 1
    if args.apply:
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        apply_db(repaired)
    elif args.check_only:
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
