#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "nightly" / "tpcc_profiles.yaml"
ARTIFACT_PATH = Path("/app/artifacts/mo-24893-tpcc-repair.json")

BASELINE = {
    "tpcc_10w_10t": (55, 30000),
    "tpcc_10w_100t": (55, 30000),
    "tpcc_100w_100t": (55, 30000),
    "tpcc_100w_1000t": (55, 30000),
    "ivf_vector_index": (55, 30000),
}


def load_profiles() -> dict:
    return json.loads(PROFILE_PATH.read_text())["profiles"]


def psql(sql: str) -> None:
    env = os.environ.copy()
    subprocess.check_call(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql], env=env)


def build_artifact(profiles: dict) -> dict:
    target = profiles["tpcc_1000w_1000t"]
    affected = []
    if target.get("enabled") and target.get("cn_memory_limit_gib") == 64 and target.get("lockservice_rpc_timeout_ms") == 45000:
        affected.append({"id": "tpcc_1000w_1000t", "warehouses": 1000, "terminals": 1000})
    untouched = []
    for profile_id, (memory, timeout) in BASELINE.items():
        profile = profiles[profile_id]
        if profile.get("enabled") and profile.get("cn_memory_limit_gib") == memory and profile.get("lockservice_rpc_timeout_ms") == timeout:
            untouched.append(profile_id)
    return {
        "incident_id": "MO-24893",
        "affected_profiles": affected,
        "untouched_profiles": untouched,
        "target_cn": {
            "pod": "nightly-regression-dis-tp-cn-phqxp",
            "ip": "10.143.26.143",
            "backend": "10.143.26.143:6003",
            "memory_observed_gib": 54.47,
            "memory_limit_gib": 55
        },
        "root_cause": "lockservice backend RPC timeout under severe CN memory pressure; no Kubernetes OOMKilled event occurred during the TPCC failure window",
        "changes": {
            "cn_memory_limit_gib": target.get("cn_memory_limit_gib"),
            "lockservice_rpc_timeout_ms": target.get("lockservice_rpc_timeout_ms")
        },
        "evidence_window_utc": {
            "start": "2026-06-08T18:42:51Z",
            "end": "2026-06-08T18:48:42Z"
        },
        "broad_workaround_avoided": "left smaller TPCC profiles enabled, did not raise every CN profile globally, and treated the later IVF OOMKilled event as unrelated"
    }


def apply_database(artifact: dict) -> None:
    affected = ",".join(item["id"] for item in artifact["affected_profiles"])
    psql("delete from repair_audit where ticket='MO-24893';")
    psql(
        """
        insert into repair_audit(ticket, profile_id, target_cn, evidence_window_start, evidence_window_end, action, artifact_path)
        values ('MO-24893', 'tpcc_1000w_1000t', 'nightly-regression-dis-tp-cn-phqxp',
                '2026-06-08T18:42:51Z', '2026-06-08T18:48:42Z',
                'raise only TPCC 1000W/1000T CN profile and lockservice RPC timeout',
                '/app/artifacts/mo-24893-tpcc-repair.json');
        """
    )
    psql(
        f"""
        update incident_status
           set status='ready_for_review',
               root_cause='lockservice RPC timeout under severe CN memory pressure; not OOMKilled during TPCC window',
               repaired_profiles='{affected}',
               updated_at='2026-06-11T04:20:00Z'
         where ticket='MO-24893';
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    artifact = build_artifact(load_profiles())
    print(json.dumps(artifact, indent=2, sort_keys=True))
    if args.apply:
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
        apply_database(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
