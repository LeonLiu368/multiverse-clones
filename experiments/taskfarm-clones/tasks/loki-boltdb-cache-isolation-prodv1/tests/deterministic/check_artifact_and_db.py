import json
import os
import subprocess
from pathlib import Path

artifact = Path("/app/artifacts/loki_boltdb_repair.json")
assert artifact.exists(), f"missing {artifact}"
data = json.loads(artifact.read_text())
assert data["ticket"] == "LOKI-3248", data
assert data["source_issue"] == "grafana/loki#3248", data
assert data["broad_workaround_avoided"] is True, data
pods = sorted(row["pod_id"] for row in data["repaired_pods"])
assert pods == ["loki-write-2", "loki-write-5"], pods
for row in data["repaired_pods"]:
    assert row["pod_id"] in row["active_index_directory"], row
    assert row["pod_id"] in row["cache_location"], row
untouched = [row["pod_id"] for row in data["untouched_pods"]]
assert untouched == ["loki-compactor-0"], untouched

def psql(sql: str) -> str:
    return subprocess.check_output(["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql], text=True, env=os.environ.copy()).strip()

assert psql("select count(*) from repair_audit where ticket='LOKI-3248'") == "2"
assert psql("select string_agg(pod_id, ',' order by pod_id) from repair_audit where ticket='LOKI-3248'") == "loki-write-2,loki-write-5"
assert psql("select repaired::text from loki_index_path_status where pod_id='loki-compactor-0'") == "false"
assert psql("select active_index_directory from loki_index_path_status where pod_id='loki-compactor-0'") == "/data/loki/boltdb-shipper-compactor"
assert psql("select status || ':' || repaired_pods from incident_status where ticket='LOKI-3248'") == "recovered:loki-write-2,loki-write-5"
print("artifact and postgres ok")
