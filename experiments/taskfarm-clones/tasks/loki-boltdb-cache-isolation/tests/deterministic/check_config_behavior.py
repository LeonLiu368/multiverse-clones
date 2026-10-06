import json
import subprocess
from pathlib import Path

out = Path("/tmp/loki_current_paths.json")
subprocess.check_call(["python3", "tools/loki_path_audit.py", "--check-only", "--output", str(out)])
data = json.loads(out.read_text())
assert data["ticket"] == "LOKI-3248", data
assert data["source_issue"] == "grafana/loki#3248", data
assert data["broad_workaround_avoided"] is True, data
pods = sorted(row["pod_id"] for row in data["repaired_pods"])
assert pods == ["loki-write-2", "loki-write-5"], pods
for row in data["repaired_pods"]:
    pod = row["pod_id"]
    assert pod in row["active_index_directory"], row
    assert pod in row["cache_location"], row
    assert row["active_index_directory"] != "/data/loki/boltdb-shipper-active", row
    assert row["cache_location"] != "/data/loki/boltdb-shipper-cache", row
untouched = {row["pod_id"]: row["reason"].lower() for row in data["untouched_pods"]}
assert "loki-compactor-0" in untouched, data
assert "compactor" in untouched["loki-compactor-0"], untouched
print("config behavior ok")
