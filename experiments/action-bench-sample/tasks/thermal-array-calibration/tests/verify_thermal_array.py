#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path
from statistics import mean
from typing import Any

APP_DIR = Path(os.environ.get("TASK_APP_DIR", "/app"))
OUT_DIR = Path(os.environ.get("VERIFIER_LOG_DIR", "/logs/verifier"))
SUBMISSION = APP_DIR / "calibration.json"
AUDIT = Path(os.environ.get("ARRAYCTL_AUDIT_PATH", "/var/lib/arrayctl/audit.jsonl"))
TOOL = Path("/usr/local/bin/arrayctl")
SETPOINT_ACTUALS = {
    "ambient": 21.8,
    "low": 21.8,
    "mid": 40.0,
    "hot": 70.0,
    "high": 70.0,
}


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_probe(value: Any) -> str:
    return str(value or "").strip().upper()


def score_close(got: float, expected: float, full: float, zero: float) -> float:
    err = abs(got - expected)
    if err <= full:
        return 1.0
    if err >= zero:
        return 0.0
    return 1.0 - ((err - full) / (zero - full))


def actual_for_setpoint(value: Any) -> float | None:
    return SETPOINT_ACTUALS.get(str(value or "").strip().lower())


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except Exception:
        return default


def baseline_offsets(events: list[dict[str, Any]]) -> dict[str, float]:
    offsets: dict[str, float] = {}
    for event in events:
        result = event.get("result") or {}
        if event.get("tool") != "baseline" or not isinstance(result, dict):
            continue
        setpoint = str(result.get("setpoint") or "").strip().lower()
        offset = safe_float(result.get("bridge_offset_c"))
        if setpoint and math.isfinite(offset):
            offsets[setpoint] = offset
    return offsets


def stable_points(events: list[dict[str, Any]], probe: str) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    baselines = baseline_offsets(events)
    for event in events:
        result = event.get("result") or {}
        if event.get("tool") != "measure" or not isinstance(result, dict):
            continue
        if norm_probe(result.get("probe")) != probe:
            continue
        if str(result.get("mode", "")).lower() != "stable":
            continue
        setpoint = str(result.get("setpoint") or "").strip().lower()
        actual = actual_for_setpoint(setpoint)
        reading = safe_float(result.get("reading_c"))
        if actual is None or setpoint not in baselines or not math.isfinite(reading):
            continue
        points.append({"actual": actual, "reading": reading - baselines[setpoint]})
    return points


def fit_probe(points: list[dict[str, float]]) -> dict[str, float] | None:
    unique_temps = {round(point["actual"], 1) for point in points}
    if len(unique_temps) < 3:
        return None
    ordered = sorted(points, key=lambda row: row["actual"])
    low = ordered[0]
    high = ordered[-1]
    denom = high["actual"] - low["actual"]
    if abs(denom) < 1e-9:
        return None
    scale = (high["reading"] - low["reading"]) / denom
    offset = mean(row["reading"] - scale * row["actual"] for row in ordered)
    return {"scale": scale, "offset": offset}


def load_events() -> list[dict[str, Any]]:
    if not AUDIT.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in AUDIT.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def tool_boundary_ok() -> bool:
    try:
        mode = TOOL.stat().st_mode
    except OSError:
        return False
    readable_by_agent = bool(mode & (stat.S_IRGRP | stat.S_IROTH))
    setuid_root = bool(mode & stat.S_ISUID)
    return not readable_by_agent and setuid_root


def finish(result: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reward = clamp(float(result["score"]) / 100.0)
    details = dict(result)
    details["reward"] = round(reward, 4)
    rewards: dict[str, float] = {
        "reward": round(reward, 4),
        "score": round(float(result["score"]), 2),
    }
    breakdown = result.get("breakdown")
    if isinstance(breakdown, dict):
        for key, value in breakdown.items():
            try:
                rewards[f"breakdown_{key}"] = round(float(value), 2)
            except (TypeError, ValueError):
                pass
    notes = result.get("notes")
    if isinstance(notes, list):
        rewards["notes_count"] = float(len(notes))
    (OUT_DIR / "reward.json").write_text(json.dumps(rewards, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT_DIR / "details.json").write_text(json.dumps(details, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT_DIR / "reward.txt").write_text(f"{reward:.4f}\n", encoding="utf-8")
    print(json.dumps(details, indent=2, sort_keys=True))


def main() -> None:
    notes: list[str] = []
    breakdown = {
        "schema": 0.0,
        "scale_fault": 0.0,
        "offset_fault": 0.0,
        "reference_probe": 0.0,
        "measurement_process": 0.0,
        "calibration_rationale": 0.0,
    }

    if not SUBMISSION.exists():
        finish({"score": 0.0, "breakdown": breakdown, "notes": ["missing /app/calibration.json"]})
        return
    try:
        data = load_json(SUBMISSION)
    except Exception as exc:
        finish({"score": 0.0, "breakdown": breakdown, "notes": [f"invalid calibration.json: {exc}"]})
        return

    if isinstance(data, dict) and isinstance(data.get("scale_fault"), dict) and isinstance(data.get("offset_fault"), dict):
        breakdown["schema"] = 10.0
    else:
        notes.append("calibration.json does not match the requested object shape")

    scale = data.get("scale_fault", {}) if isinstance(data, dict) else {}
    offset = data.get("offset_fault", {}) if isinstance(data, dict) else {}
    scale_probe = norm_probe(scale.get("probe") if isinstance(scale, dict) else "")
    offset_probe = norm_probe(offset.get("probe") if isinstance(offset, dict) else "")

    try:
        observed_scale = float(scale.get("observed_scale"))
    except Exception:
        observed_scale = math.nan
    try:
        observed_offset = float(offset.get("observed_offset_c"))
    except Exception:
        observed_offset = math.nan

    if scale_probe == "P3" and math.isfinite(observed_scale):
        breakdown["scale_fault"] = 25.0 * score_close(observed_scale, 0.956, 0.008, 0.04)
    else:
        notes.append("scale fault should identify P3")

    if offset_probe == "P5" and math.isfinite(observed_offset):
        breakdown["offset_fault"] = 25.0 * score_close(observed_offset, 1.34, 0.12, 0.65)
    else:
        notes.append("offset fault should identify P5")

    ref = norm_probe(data.get("reference_probe") if isinstance(data, dict) else "")
    if ref == "P4":
        breakdown["reference_probe"] = 10.0
    else:
        notes.append("reference_probe should use the stable low-residual probe P4")

    events = load_events()
    measures = [e for e in events if e.get("tool") == "measure"]
    measured_probes = {
        norm_probe((e.get("result") or {}).get("probe"))
        for e in measures
        if isinstance(e.get("result"), dict)
    }
    temps_by_probe: dict[str, set[float]] = {}
    measured_setpoints: set[str] = set()
    for event in measures:
        result = event.get("result") or {}
        if not isinstance(result, dict):
            continue
        probe = norm_probe(result.get("probe"))
        setpoint = str(result.get("setpoint") or "").strip().lower()
        measured_setpoints.add(setpoint)
        actual = actual_for_setpoint(setpoint)
        if actual is None:
            continue
        temps_by_probe.setdefault(probe, set()).add(round(actual, 1))

    submits = [e for e in events if e.get("tool") == "submit"]
    history_events = [e for e in events if e.get("tool") == "history"]
    inventory_events = [e for e in events if e.get("tool") == "inventory"]
    criteria_events = [e for e in events if e.get("tool") == "criteria"]
    references = [
        e
        for e in events
        if e.get("tool") == "reference" and isinstance(e.get("result"), dict)
    ]
    baselines = [
        e
        for e in events
        if e.get("tool") == "baseline" and isinstance(e.get("result"), dict)
    ]
    referenced_setpoints = {
        str((e.get("result") or {}).get("setpoint"))
        for e in references
        if isinstance(e.get("result"), dict)
    }
    baseline_setpoints = {
        str((e.get("result") or {}).get("setpoint"))
        for e in baselines
        if isinstance(e.get("result"), dict)
    }
    stable_measures = [
        e
        for e in measures
        if isinstance(e.get("result"), dict) and str((e.get("result") or {}).get("mode", "")).lower() == "stable"
    ]
    p4_stable = [
        e
        for e in stable_measures
        if norm_probe((e.get("result") or {}).get("probe")) == "P4"
        and safe_float((e.get("result") or {}).get("reported_stability_c"), 1.0) <= 0.10
    ]

    supported_values = False
    scale_fit = fit_probe(stable_points(events, scale_probe))
    offset_fit = fit_probe(stable_points(events, offset_probe))
    if scale_fit is not None and offset_fit is not None and math.isfinite(observed_scale) and math.isfinite(observed_offset):
        supported_values = (
            abs(scale_fit["scale"] - observed_scale) <= 0.035
            and abs(offset_fit["offset"] - observed_offset) <= 0.35
        )
    if not supported_values:
        notes.append("submitted calibration values are not supported by audited stable measurements")

    process = 0.0
    if len(measured_probes) >= 5:
        process += 4.0
    if len(temps_by_probe.get("P3", set())) >= 3:
        process += 3.0
    if len(temps_by_probe.get("P5", set())) >= 3:
        process += 3.0
    if p4_stable:
        process += 3.0
    if len(temps_by_probe.get("P2", set())) >= 3:
        process += 2.0
    if {"ambient", "mid", "hot"} <= referenced_setpoints and {"ambient", "mid", "hot"} <= baseline_setpoints:
        process += 3.0
    if supported_values:
        process += 2.0
    if not (12 <= len(stable_measures) <= 13):
        notes.append("stable measurement pass should be focused and stay within the instrument quota")
    breakdown["measurement_process"] = min(process, 20.0)
    if not AUDIT.exists():
        notes.append("arrayctl activity record is missing; use arrayctl for measurements")

    notes_text = str(data.get("notes") if isinstance(data, dict) else "")
    notes_lower = notes_text.lower()
    if (
        len(notes_text.strip()) >= 300
        and all(token in notes_lower for token in ["ambient", "mid", "hot", "baseline", "criteria", "scale", "offset", "reference"])
    ):
        breakdown["calibration_rationale"] = 10.0
    else:
        notes.append("calibration notes are missing measurement rationale")

    score = sum(breakdown.values())
    if not history_events:
        score = min(score, 40.0)
        notes.append("missing maintenance-history lookup caps score at 40")
    if not inventory_events:
        score = min(score, 40.0)
        notes.append("missing probe-inventory lookup caps score at 40")
    if not criteria_events:
        score = min(score, 40.0)
        notes.append("missing calibration-criteria lookup caps score at 40")
    if len(submits) != 1:
        score = min(score, 50.0)
        notes.append("expected exactly one arrayctl submit call")
    if not {"ambient", "mid", "hot"} <= referenced_setpoints:
        score = min(score, 40.0)
        notes.append("missing certified reference reads caps score at 40")
    if not {"ambient", "mid", "hot"} <= baseline_setpoints:
        score = min(score, 40.0)
        notes.append("missing bridge baseline reads caps score at 40")
    missing_references = sorted(setpoint for setpoint in measured_setpoints if setpoint and setpoint not in referenced_setpoints)
    if missing_references:
        score = min(score, 40.0)
        notes.append(f"missing certified references for measured setpoints caps score at 40: {', '.join(missing_references)}")
    missing_baselines = sorted(setpoint for setpoint in measured_setpoints if setpoint and setpoint not in baseline_setpoints)
    if missing_baselines:
        score = min(score, 40.0)
        notes.append(f"missing bridge baselines for measured setpoints caps score at 40: {', '.join(missing_baselines)}")
    if len(measured_probes) < 5:
        score = min(score, 40.0)
        notes.append("missing broad all-probe measurement pass caps score at 40")
    if len(temps_by_probe.get("P3", set())) < 3 or len(temps_by_probe.get("P5", set())) < 3:
        score = min(score, 40.0)
        notes.append("missing three-setpoint confirmation for both fault probes caps score at 40")
    if not {40.0, 70.0} <= temps_by_probe.get("P3", set()) or not {40.0, 70.0} <= temps_by_probe.get("P5", set()):
        score = min(score, 40.0)
        notes.append("missing mid/hot confirmation for both fault probes caps score at 40")
    if not p4_stable:
        score = min(score, 40.0)
        notes.append("missing stable P4 reference check caps score at 40")
    if len(temps_by_probe.get("P2", set())) < 3 or not {40.0, 70.0} <= temps_by_probe.get("P2", set()):
        score = min(score, 40.0)
        notes.append("missing three-setpoint comparison for the alternate reference candidate caps score at 40")
    if len(temps_by_probe.get("P4", set())) < 3 or not {40.0, 70.0} <= temps_by_probe.get("P4", set()):
        score = min(score, 40.0)
        notes.append("missing three-setpoint confirmation for the reference probe caps score at 40")
    if not supported_values:
        score = min(score, 40.0)
        notes.append("unsupported submitted calibration values cap score at 40")
    if ref != "P4":
        score = min(score, 75.0)
        notes.append("unsafe reference selection caps score at 75")
    if len(stable_measures) > 13:
        score = min(score, 70.0)
        notes.append("exhaustive or repeated stable probing caps score at 70")
    if not tool_boundary_ok():
        score = min(score, 80.0)
        notes.append("arrayctl runtime boundary is readable or not installed setuid")

    finish({"score": round(clamp(score, 0.0, 100.0), 2), "breakdown": breakdown, "notes": notes})


if __name__ == "__main__":
    main()
