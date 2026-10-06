import json
import os
import subprocess
from pathlib import Path

artifact_path = Path("/app/artifacts/mo-24893-tpcc-repair.json")
assert artifact_path.exists(), f"missing {artifact_path}"
data = json.loads(artifact_path.read_text())
required = {
    "incident_id",
    "affected_profiles",
    "untouched_profiles",
    "target_cn",
    "root_cause",
    "changes",
    "evidence_window_utc",
    "broad_workaround_avoided",
}
assert required <= set(data), sorted(set(data) ^ required)
assert data["incident_id"] == "MO-24893"
assert data["affected_profiles"] == [{"id": "tpcc_1000w_1000t", "warehouses": 1000, "terminals": 1000}], data["affected_profiles"]
untouched = set(data["untouched_profiles"])
for profile_id in ["tpcc_10w_10t", "tpcc_10w_100t", "tpcc_100w_100t", "tpcc_100w_1000t", "ivf_vector_index"]:
    assert profile_id in untouched, data["untouched_profiles"]
assert data["target_cn"]["pod"] == "nightly-regression-dis-tp-cn-phqxp"
assert data["target_cn"]["backend"] == "10.143.26.143:6003"
assert data["changes"]["cn_memory_limit_gib"] == 64
assert data["changes"]["lockservice_rpc_timeout_ms"] == 45000
root = (data["root_cause"] + " " + data["broad_workaround_avoided"]).lower()
assert "lockservice" in root and "memory pressure" in root, root
assert "not oomkilled" in root or "no kubernetes oomkilled" in root or "oomkilled event as unrelated" in root, root
assert data["evidence_window_utc"] == {"start": "2026-06-08T18:42:51Z", "end": "2026-06-08T18:48:42Z"}

profiles = json.loads(Path("/app/src/nightly/tpcc_profiles.yaml").read_text())["profiles"]
assert profiles["tpcc_1000w_1000t"]["enabled"] is True
assert profiles["tpcc_1000w_1000t"]["cn_memory_limit_gib"] == 64
assert profiles["tpcc_1000w_1000t"]["lockservice_rpc_timeout_ms"] == 45000
for profile_id in ["tpcc_10w_10t", "tpcc_10w_100t", "tpcc_100w_100t", "tpcc_100w_1000t", "ivf_vector_index"]:
    profile = profiles[profile_id]
    assert profile["enabled"] is True, profile
    assert profile["cn_memory_limit_gib"] == 55, profile
    assert profile["lockservice_rpc_timeout_ms"] == 30000, profile

def psql(sql: str) -> str:
    return subprocess.check_output(
        ["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
        text=True,
        env=os.environ.copy(),
    ).strip()

assert psql("select count(*) from repair_audit where ticket='MO-24893'") == "1"
assert psql("select profile_id || ':' || target_cn from repair_audit where ticket='MO-24893'") == "tpcc_1000w_1000t:nightly-regression-dis-tp-cn-phqxp"
status = psql("select status || ':' || repaired_profiles from incident_status where ticket='MO-24893'")
assert status == "ready_for_review:tpcc_1000w_1000t", status
unchanged = psql("select string_agg(profile_id, ',' order by profile_id) from tpcc_profile_evidence where current_action='leave'")
assert unchanged == "ivf_vector_index,tpcc_100w_1000t,tpcc_100w_100t,tpcc_10w_100t,tpcc_10w_10t", unchanged
print("artifact, config, and postgres ok")
