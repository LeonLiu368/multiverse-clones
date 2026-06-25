"""Logfire fetch shaping with a fake query client (no token needed)."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spoink.logfire_export import fetch, _lvl, _host  # noqa: E402

INCIDENT = [
    {"start_timestamp": "2026-06-24T23:00:00Z", "service_name": "oddish-backend", "level": 17, "message": "GET /tasks"},
    {"start_timestamp": "2026-06-24T23:30:00Z", "service_name": "oddish-worker", "level": 13, "message": "slow query"},
]
OVERVIEW = [
    {"message": "GET /tasks", "service_name": "oddish-backend", "n": 200, "level": 17,
     "exception_type": "HTTPException", "exception_message": "500"},
]


class FakeLF:
    def query(self, sql, min_ts, max_ts=None, limit=10000):
        return OVERVIEW if "GROUP BY" in sql else INCIDENT


def test_level_names_and_host():
    assert _lvl(9) == "info" and _lvl(13) == "warn" and _lvl(17) == "error"
    assert _host("pylf_v1_us_x").endswith("logfire-us.pydantic.dev/v2/query")
    assert "logfire-eu" in _host("pylf_v1_eu_x")


def test_fetch_shapes_incident_and_overview():
    d = fetch(FakeLF(), "2026-06-24T22:34:00Z", "2026-06-25T00:34:00Z", "2025-06-25T00:34:00Z")
    assert d["meta"]["now"] == "2026-06-25T00:34:00Z" and d["meta"]["workspace"] == "oddish"
    assert d["meta"]["incident_window"] == ["2026-06-24T22:34:00Z", "2026-06-25T00:34:00Z"]
    # level numbers resolved to names on both views
    assert [r["level_name"] for r in d["incident"]] == ["error", "warn"]
    assert d["overview"][0]["level_name"] == "error" and d["overview"][0]["n"] == 200
