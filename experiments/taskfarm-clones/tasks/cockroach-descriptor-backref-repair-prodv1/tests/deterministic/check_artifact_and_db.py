import json
import os
import subprocess
from pathlib import Path


ARTIFACT = Path("/app/artifacts/descriptor_backref_repair.json")
EXPECTED = {193, 211}
UNTOUCHED = {244, 305, 318}


def psql(sql: str) -> list[list[str]]:
    cmd = [
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-h",
        os.getenv("PGHOST", "postgres"),
        "-U",
        os.getenv("PGUSER", "agent"),
        "-d",
        os.getenv("PGDATABASE", "crdb_descriptor_backref_repair"),
        "-At",
        "-F",
        "\t",
        "-c",
        sql,
    ]
    out = subprocess.check_output(cmd, text=True)
    return [line.split("\t") for line in out.splitlines() if line]


assert ARTIFACT.exists(), "missing descriptor_backref_repair.json"
data = json.loads(ARTIFACT.read_text())
assert data.get("ticket") == "CRDB-63963", data
assert data.get("sentry_event") == "evt-crdb-170371", data
assert data.get("artifact_version") == 1, data
assert set(data.get("affected_descriptor_ids", [])) == EXPECTED, data
assert set(data.get("untouched_descriptor_ids", [])) == UNTOUCHED, data
assert "validation" in data.get("broad_workaround_rejected", "").lower(), data
assert "only" in data.get("broad_workaround_rejected", "").lower() or "scoped" in data.get("broad_workaround_rejected", "").lower(), data

repairs = data.get("repairs")
assert isinstance(repairs, list) and len(repairs) == 2, data
for repair in repairs:
    assert repair.get("relation_id") in EXPECTED, repair
    assert isinstance(repair.get("relation_name"), str) and repair["relation_name"], repair
    assert isinstance(repair.get("referenced_descriptor_id"), int), repair
    assert repair.get("action") == "remove_depended_on_by_backref", repair
    assert "missing" in repair.get("reason", "").lower() or "not found" in repair.get("reason", "").lower(), repair

rows = psql(
    """
SELECT relation_id, repair_action, repair_status
FROM descriptor_backrefs
WHERE relation_id IN (193,211,244,305,318)
ORDER BY relation_id;
"""
)
state = {int(row[0]): (row[1], row[2]) for row in rows}
for relation_id in EXPECTED:
    assert state[relation_id] == ("remove_depended_on_by_backref", "ready"), state
for relation_id in UNTOUCHED:
    assert state[relation_id] == ("pending", "unreviewed"), state

audit_rows = psql("SELECT relation_id, action, artifact_path FROM descriptor_repair_audit ORDER BY relation_id;")
assert len(audit_rows) == 2, audit_rows
assert {int(row[0]) for row in audit_rows} == EXPECTED, audit_rows
assert all(row[1] == "remove_depended_on_by_backref" for row in audit_rows), audit_rows
assert all(row[2] == "/app/artifacts/descriptor_backref_repair.json" for row in audit_rows), audit_rows

incident = psql("SELECT status FROM descriptor_incidents WHERE ticket_id = 'CRDB-63963';")
assert incident == [["repair_ready"]], incident
print("artifact and db ok")
