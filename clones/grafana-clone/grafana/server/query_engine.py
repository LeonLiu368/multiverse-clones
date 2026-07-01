from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .state import GrafanaStore


METRIC_NAME_RE = re.compile(r"([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(?:\{|\[|$)")
SELECTOR_RE = re.compile(r"\{([^{}]*)\}")
LOKI_FILTER_RE = re.compile(r"^\s*(\{[^{}]*\})\s*(?:\|=\s*\"([^\"]*)\")?\s*$")


def normalize_query(expr: str) -> str:
    text = " ".join(str(expr).strip().split())
    text = re.sub(r"\s*([(),{}\[\]=])\s*", r"\1", text)
    text = SELECTOR_RE.sub(lambda match: "{" + _normalize_labels(match.group(1)) + "}", text)
    return text


def _normalize_labels(labels: str) -> str:
    parts = []
    for raw in labels.split(","):
        item = raw.strip()
        if not item:
            continue
        key, sep, value = item.partition("=")
        if not sep:
            parts.append(item)
            continue
        parts.append(f"{key.strip()}={value.strip()}")
    return ",".join(sorted(parts))


def prometheus_query(
    store: GrafanaStore,
    expr: str,
    datasource_uid: str | None = None,
    since: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict[str, Any]:
    fixtures = store.state.get("metrics", {}).get("queries", {})
    result = fixtures.get(expr)
    matched = "exact" if result is not None else None
    if result is None:
        wanted = normalize_query(expr)
        for fixture_expr, fixture_result in fixtures.items():
            if normalize_query(fixture_expr) == wanted:
                result = fixture_result
                matched = "normalized"
                break

    if result is None:
        result = {"resultType": "matrix", "series": []}
        matched = "none"

    start, end = _time_bounds(store, since=since, from_time=from_time, to_time=to_time)
    return {
        "status": "success",
        "datasource_uid": datasource_uid,
        "query": expr,
        "match": matched,
        "range": _range_payload(start, end),
        "data": _prometheus_data(result, start, end),
    }


def _prometheus_data(
    result: dict[str, Any],
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    result_type = result.get("resultType", "matrix")
    series = copy.deepcopy(result.get("series", []))
    return {
        "resultType": result_type,
        "result": [
            {
                "metric": item.get("metric", {}),
                "values": _coerce_values(item.get("values", []), start, end),
            }
            for item in series
        ],
    }


def _coerce_values(values: list[Any], start: datetime | None = None, end: datetime | None = None) -> list[list[Any]]:
    coerced = []
    for value in values:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            ts = _parse_time(str(value[0]))
            if not _in_range(ts, start, end):
                continue
            coerced.append([value[0], value[1]])
    return coerced


def loki_query(
    store: GrafanaStore,
    expr: str,
    datasource_uid: str | None = None,
    limit: int | None = None,
    since: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict[str, Any]:
    fixtures = store.state.get("logs", {}).get("queries", {})
    entries: list[dict[str, Any]]
    matched = "exact"
    if expr in fixtures:
        entries = copy.deepcopy(fixtures[expr].get("entries", []))
    else:
        matched = "filter"
        entries = _filter_log_entries(all_log_entries(store), expr)

    start, end = _time_bounds(store, since=since, from_time=from_time, to_time=to_time)
    entries = [entry for entry in entries if _in_range(_parse_time(str(entry.get("ts", ""))), start, end)]

    if limit is not None:
        entries = entries[:limit]

    return {
        "status": "success",
        "datasource_uid": datasource_uid,
        "query": expr,
        "match": matched,
        "range": _range_payload(start, end),
        "data": {
            "resultType": "streams",
            "result": _streams_from_entries(entries),
            "entries": entries,
        },
    }


def all_log_entries(store: GrafanaStore) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for fixture in store.state.get("logs", {}).get("queries", {}).values():
        for entry in fixture.get("entries", []):
            if entry not in entries:
                entries.append(copy.deepcopy(entry))
    return entries


def _filter_log_entries(entries: list[dict[str, Any]], expr: str) -> list[dict[str, Any]]:
    match = LOKI_FILTER_RE.match(expr)
    if not match:
        return []
    selector = _parse_selector(match.group(1))
    contains = match.group(2)
    results = []
    for entry in entries:
        labels = entry.get("labels", {})
        if any(str(labels.get(key)) != value for key, value in selector.items()):
            continue
        if contains and contains not in str(entry.get("line", "")):
            continue
        results.append(entry)
    return results


def _parse_selector(selector: str) -> dict[str, str]:
    content = selector.strip().strip("{}").strip()
    if not content:
        return {}
    parsed: dict[str, str] = {}
    for part in content.split(","):
        key, sep, value = part.partition("=")
        if sep:
            parsed[key.strip()] = value.strip().strip('"')
    return parsed


def _streams_from_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[tuple[str, str], ...], list[list[str]]] = {}
    labels_by_key: dict[tuple[tuple[str, str], ...], dict[str, str]] = {}
    for entry in entries:
        labels = {str(k): str(v) for k, v in (entry.get("labels") or {}).items()}
        key = tuple(sorted(labels.items()))
        labels_by_key[key] = labels
        grouped.setdefault(key, []).append([str(entry.get("ts", "")), str(entry.get("line", ""))])
    return [{"stream": labels_by_key[key], "values": values} for key, values in grouped.items()]


def metric_names(store: GrafanaStore) -> list[str]:
    names: set[str] = set()
    for expr in store.state.get("metrics", {}).get("queries", {}):
        for name in METRIC_NAME_RE.findall(expr):
            if name not in {"by", "sum", "rate", "increase", "avg", "max", "min", "count"}:
                names.add(name)
    return sorted(names)


def metric_label_names(store: GrafanaStore) -> list[str]:
    names: set[str] = set()
    for expr, result in store.state.get("metrics", {}).get("queries", {}).items():
        for selector in SELECTOR_RE.findall(expr):
            names.update(_parse_selector("{" + selector + "}").keys())
        for series in result.get("series", []):
            names.update(str(key) for key in (series.get("metric") or {}).keys())
    return sorted(names)


def metric_label_values(store: GrafanaStore, label: str) -> list[str]:
    values: set[str] = set()
    for expr, result in store.state.get("metrics", {}).get("queries", {}).items():
        for selector in SELECTOR_RE.findall(expr):
            value = _parse_selector("{" + selector + "}").get(label)
            if value is not None:
                values.add(value)
        for series in result.get("series", []):
            metric = series.get("metric") or {}
            if label in metric:
                values.add(str(metric[label]))
    return sorted(values)


def log_label_names(store: GrafanaStore) -> list[str]:
    names: set[str] = set()
    for expr in store.state.get("logs", {}).get("queries", {}):
        match = LOKI_FILTER_RE.match(expr)
        if match:
            names.update(_parse_selector(match.group(1)).keys())
    for entry in all_log_entries(store):
        names.update(str(key) for key in (entry.get("labels") or {}).keys())
    return sorted(names)


def log_label_values(store: GrafanaStore, label: str) -> list[str]:
    values: set[str] = set()
    for expr in store.state.get("logs", {}).get("queries", {}):
        match = LOKI_FILTER_RE.match(expr)
        if match:
            value = _parse_selector(match.group(1)).get(label)
            if value is not None:
                values.add(value)
    for entry in all_log_entries(store):
        labels = entry.get("labels") or {}
        if label in labels:
            values.add(str(labels[label]))
    return sorted(values)


def ds_query(store: GrafanaStore, payload: dict[str, Any]) -> dict[str, Any]:
    queries = payload.get("queries") or []
    results: dict[str, Any] = {}
    for index, query in enumerate(queries):
        ref_id = str(query.get("refId") or chr(ord("A") + index))
        datasource_uid = _datasource_uid(query)
        query_type = query.get("queryType") or query.get("type") or _infer_query_type(store, datasource_uid)
        expr = str(query.get("expr") or query.get("query") or "")
        try:
            data_block = _run_query_type(store, query_type, expr, datasource_uid, query)
            results[ref_id] = {
                "status": 200,
                # Real Grafana returns dataframes under `frames`; keep the clone-native
                # `data` block too so the gcx CLI / MCP (which read it) don't break.
                "frames": _frames_from_result(ref_id, query_type, data_block),
                "data": data_block,
            }
        except ValueError as exc:
            results[ref_id] = {"status": 400, "error": str(exc)}
    return {"results": results}


def _epoch_ms(ts: Any) -> int | None:
    dt = _parse_time(str(ts))
    return int(dt.timestamp() * 1000) if dt is not None else None


def _frames_from_result(ref_id: str, query_type: str, data_block: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a query result into real Grafana dataframes (schema.fields + data.values)."""
    inner = data_block.get("data") if isinstance(data_block, dict) else None
    if not isinstance(inner, dict):
        return []
    series = inner.get("result") or []
    frames: list[dict[str, Any]] = []

    if query_type in {"metrics", "prometheus", "promql"}:
        for item in series:
            labels = {str(k): str(v) for k, v in (item.get("metric") or {}).items()}
            pairs = item.get("values")
            if pairs is None and item.get("value") is not None:
                pairs = [item["value"]]
            times: list[int] = []
            vals: list[float | None] = []
            for pair in pairs or []:
                if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
                    continue
                ms = _epoch_ms(pair[0])
                if ms is None:
                    continue
                times.append(ms)
                try:
                    vals.append(float(pair[1]))
                except (TypeError, ValueError):
                    vals.append(None)
            value_name = labels.get("__name__") or "Value"
            frames.append({
                "schema": {
                    "refId": ref_id,
                    "fields": [
                        {"name": "Time", "type": "time", "typeInfo": {"frame": "time.Time"}},
                        {"name": value_name, "type": "number", "labels": labels, "typeInfo": {"frame": "float64"}},
                    ],
                },
                "data": {"values": [times, vals]},
            })
        return frames

    if query_type in {"logs", "loki", "logql"}:
        times = []
        lines: list[str] = []
        labels_col: list[dict[str, str]] = []
        for stream in series:
            stream_labels = {str(k): str(v) for k, v in (stream.get("stream") or {}).items()}
            for pair in stream.get("values") or []:
                if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
                    continue
                ms = _epoch_ms(pair[0])
                if ms is None:
                    continue
                times.append(ms)
                lines.append(str(pair[1]))
                labels_col.append(stream_labels)
        if not times:
            return []
        frames.append({
            "schema": {
                "refId": ref_id,
                "meta": {"preferredVisualisationType": "logs"},
                "fields": [
                    {"name": "labels", "type": "other", "typeInfo": {"frame": "json.RawMessage"}},
                    {"name": "Time", "type": "time", "typeInfo": {"frame": "time.Time"}},
                    {"name": "Line", "type": "string", "typeInfo": {"frame": "string"}},
                ],
            },
            "data": {"values": [labels_col, times, lines]},
        })
        return frames

    return []


def _run_query_type(
    store: GrafanaStore,
    query_type: str,
    expr: str,
    datasource_uid: str | None,
    query: dict[str, Any],
) -> Any:
    if query_type in {"metrics", "prometheus", "promql"}:
        return prometheus_query(
            store,
            expr,
            datasource_uid,
            since=query.get("since"),
            from_time=query.get("from") or query.get("from_time"),
            to_time=query.get("to") or query.get("to_time"),
        )
    if query_type in {"logs", "loki", "logql"}:
        return loki_query(
            store,
            expr,
            datasource_uid,
            limit=query.get("limit"),
            since=query.get("since"),
            from_time=query.get("from") or query.get("from_time"),
            to_time=query.get("to") or query.get("to_time"),
        )
    if query_type == "metric_names":
        return {"metricNames": metric_names(store)}
    if query_type == "metric_labels":
        return {"labels": metric_label_names(store)}
    if query_type == "metric_label_values":
        label = query.get("label")
        if not label:
            raise ValueError("label is required")
        return {"label": label, "values": metric_label_values(store, str(label))}
    if query_type == "log_labels":
        return {"labels": log_label_names(store)}
    if query_type == "log_label_values":
        label = query.get("label")
        if not label:
            raise ValueError("label is required")
        return {"label": label, "values": log_label_values(store, str(label))}
    raise ValueError(f"unsupported query type: {query_type}")


def _datasource_uid(query: dict[str, Any]) -> str | None:
    datasource = query.get("datasource")
    if isinstance(datasource, dict):
        return datasource.get("uid")
    return query.get("datasource_uid")


def _infer_query_type(store: GrafanaStore, datasource_uid: str | None) -> str:
    if datasource_uid:
        datasource = store.datasource(datasource_uid)
        if datasource and datasource.get("type") == "loki":
            return "logs"
    return "metrics"


def _time_bounds(
    store: GrafanaStore,
    since: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> tuple[datetime | None, datetime | None]:
    now = _parse_time(store.meta_now()) or datetime.now(timezone.utc)
    end = _parse_relative_time(to_time, now) if to_time else (now if since or from_time else None)
    start = _parse_relative_time(from_time, now) if from_time else None
    if start is None and since:
        start = now - _parse_duration(str(since))
    return start, end


def _range_payload(start: datetime | None, end: datetime | None) -> dict[str, str | None]:
    return {"from": _format_time(start), "to": _format_time(end)}


def _format_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_relative_time(value: str | None, now: datetime) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text == "now":
        return now
    if text.startswith("now-"):
        return now - _parse_duration(text.removeprefix("now-"))
    return _parse_time(text)


def _parse_time(value: str) -> datetime | None:
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        number = int(text)
        if number > 10_000_000_000:
            number = number // 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_duration(value: str) -> timedelta:
    match = re.fullmatch(r"\s*(\d+)\s*([smhdw])\s*", str(value))
    if not match:
        return timedelta(hours=1)
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return timedelta(weeks=amount)


def _in_range(value: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    if value is None:
        return True
    if start is not None and value < start:
        return False
    if end is not None and value > end:
        return False
    return True
