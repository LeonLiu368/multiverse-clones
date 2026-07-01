"""Logfire clone seed viewer — a `records.json` corpus (the shape abundant-logfire-clone bakes and
serves via its SQL Query API over a DuckDB `records` table). Each record is an OTel span/log with
trace/span ids, a numeric `level`, `duration`, `service_name`, exception_* and http_* columns. We
group them into traces (span tree + waterfall offsets) and render them Pydantic-Logfire-style.
Read-only."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from adapters.fileseed import FileSeedAdapter

# OTel severity numbers Logfire uses (spoink LEVEL_NAMES).
LEVEL_NAMES = {1: "trace", 5: "debug", 9: "info", 13: "warn", 17: "error", 21: "fatal"}
_NAME_LEVEL = {v: k for k, v in LEVEL_NAMES.items()}
# core columns promoted onto the span; everything else is surfaced as an attribute row in the detail
_CORE = {
    "trace_id", "span_id", "parent_span_id", "span_name", "message", "level", "service_name",
    "start_timestamp", "end_timestamp", "duration", "is_exception", "exception_type",
    "exception_message", "exception_stacktrace", "http_method", "http_route", "http_status_code",
    "http_url", "kind", "otel_status_code",
}


def _epoch(ts: Any) -> float | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).replace(tzinfo=datetime.fromisoformat(s).tzinfo or timezone.utc).timestamp()
    except Exception:
        try:
            return datetime.fromisoformat(s.split("+")[0]).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            return None


def _level_num(v: Any) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    return _NAME_LEVEL.get(str(v).lower(), 9)


class LogfireAdapter(FileSeedAdapter):
    id = "logfire"
    display_name = "Logfire"
    status = "active"
    ui_module = "logfire"
    sample_files = ("logfire.records.json",)
    # multiverse-clones bakes the corpus into `logfire-service:prod-v1` as a GZIPPED file at
    # /data/records.json.gz (Dockerfile.prod-v1, ENV LOGFIRE_BAKED). The FileSeed base transparently
    # gunzips it. Older logfire-gateway / uncompressed paths kept for back-compat.
    image_substrings = ("logfire-service", "logfire-gateway", "logfire-seed")
    image_state_paths = ("/data/records.json.gz", "/data/records.json", "/records.json")

    def _norm(self, r: dict[str, Any]) -> dict[str, Any]:
        lvl = _level_num(r.get("level"))
        start = _epoch(r.get("start_timestamp"))
        dur = r.get("duration")
        if isinstance(dur, (int, float)):
            dur_s = float(dur)
        else:
            end = _epoch(r.get("end_timestamp"))
            dur_s = (end - start) if (start is not None and end is not None) else 0.0
        attrs = sorted(
            (k, r[k]) for k in r
            if k not in _CORE and r[k] not in (None, "", [], {}) and not k.startswith("_")
        )
        return {
            "trace_id": r.get("trace_id") or "",
            "span_id": r.get("span_id") or "",
            "parent_span_id": r.get("parent_span_id") or None,
            "name": r.get("span_name") or r.get("message") or "(span)",
            "message": r.get("message") or r.get("span_name") or "",
            "level": lvl,
            "level_name": LEVEL_NAMES.get(lvl, str(lvl)),
            "service_name": r.get("service_name") or "",
            "start_timestamp": r.get("start_timestamp"),
            "start_epoch": start,
            "duration_ms": round(max(dur_s, 0.0) * 1000, 3),
            "is_exception": bool(r.get("is_exception")),
            "exception_type": r.get("exception_type"),
            "exception_message": r.get("exception_message"),
            "exception_stacktrace": r.get("exception_stacktrace"),
            "http_method": r.get("http_method"),
            "http_route": r.get("http_route"),
            "http_status_code": r.get("http_status_code"),
            "http_url": r.get("http_url"),
            "kind": r.get("kind"),
            "otel_status_code": r.get("otel_status_code"),
            "attributes": [{"key": k, "value": v} for k, v in attrs],
        }

    def _build_trace(self, tid: str, spans: list[dict]) -> dict[str, Any]:
        ids = {s["span_id"] for s in spans}
        children: dict[str | None, list[dict]] = {}
        for s in spans:
            parent = s["parent_span_id"] if s["parent_span_id"] in ids else None
            children.setdefault(parent, []).append(s)
        for lst in children.values():
            lst.sort(key=lambda s: (s["start_epoch"] or 0, s["span_id"]))
        starts = [s["start_epoch"] for s in spans if s["start_epoch"] is not None]
        t0 = min(starts) if starts else 0.0
        total_ms = 0.0
        for s in spans:
            if s["start_epoch"] is not None:
                total_ms = max(total_ms, (s["start_epoch"] - t0) * 1000 + s["duration_ms"])

        ordered: list[dict] = []

        def walk(parent: str | None, depth: int) -> None:
            for s in children.get(parent, []):
                offset = ((s["start_epoch"] - t0) * 1000) if s["start_epoch"] is not None else 0.0
                ordered.append({**s, "depth": depth, "offset_ms": round(offset, 3)})
                walk(s["span_id"], depth + 1)

        walk(None, 0)
        # any orphans (shouldn't happen) appended flat
        seen = {s["span_id"] for s in ordered}
        for s in spans:
            if s["span_id"] not in seen:
                ordered.append({**s, "depth": 0, "offset_ms": 0.0})

        root = ordered[0] if ordered else {}
        errs = [s for s in spans if s["level"] >= 17 or s["is_exception"]]
        return {
            "trace_id": tid,
            "root_name": root.get("name", "(trace)"),
            "service_name": root.get("service_name", ""),
            "start_timestamp": root.get("start_timestamp"),
            "start_epoch": t0,
            "duration_ms": round(total_ms, 3),
            "span_count": len(spans),
            "error_count": len(errs),
            "level": max((s["level"] for s in spans), default=9),
            "level_name": LEVEL_NAMES.get(max((s["level"] for s in spans), default=9), "info"),
            "spans": ordered,
        }

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        d = json.loads(raw)
        rows = d if isinstance(d, list) else (d.get("records") or d.get("data") or [])
        spans = [self._norm(r) for r in rows if isinstance(r, dict)]

        by_trace: dict[str, list[dict]] = {}
        for s in spans:
            by_trace.setdefault(s["trace_id"] or s["span_id"], []).append(s)
        traces = [self._build_trace(tid, ss) for tid, ss in by_trace.items()]
        traces.sort(key=lambda t: (t["start_epoch"] or 0), reverse=True)

        records = sorted(spans, key=lambda s: (s["start_epoch"] or 0), reverse=True)
        services = sorted({s["service_name"] for s in spans if s["service_name"]})
        return {
            "meta": {"source": "logfire", "path": path},
            "records": records,
            "traces": traces,
            "services": services,
            "levels": LEVEL_NAMES,
            "stats": {
                "records": len(spans),
                "traces": len(traces),
                "services": len(services),
                "errors": sum(1 for s in spans if s["level"] >= 17),
                "exceptions": sum(1 for s in spans if s["is_exception"]),
            },
        }
