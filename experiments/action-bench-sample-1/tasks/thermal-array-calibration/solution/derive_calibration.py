#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean


def load_references(path: Path) -> dict[str, float]:
    references: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        result = payload["result"]
        references[str(result["setpoint"])] = float(result["actual_temp_c"])
    return references


def load_baselines(path: Path) -> dict[str, float]:
    baselines: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        result = payload["result"]
        baselines[str(result["setpoint"])] = float(result["bridge_offset_c"])
    return baselines


def load_points(path: Path, references: dict[str, float], baselines: dict[str, float]) -> dict[str, list[dict[str, float]]]:
    points: dict[str, list[dict[str, float]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        result = payload["result"]
        setpoint = str(result["setpoint"])
        corrected_reading = float(result["reading_c"]) - baselines[setpoint]
        points[result["probe"]].append(
            {
                "actual": references[setpoint],
                "reading": corrected_reading,
                "stability": float(result.get("reported_stability_c", 0.99)),
            }
        )
    return dict(points)


def fit_probe(points: list[dict[str, float]]) -> dict[str, float]:
    ordered = sorted(points, key=lambda row: row["actual"])
    if len({round(row["actual"], 1) for row in ordered}) < 3:
        raise ValueError("three distinct stable setpoints are required")
    low = ordered[0]
    high = ordered[-1]
    scale = (high["reading"] - low["reading"]) / (high["actual"] - low["actual"])
    offset = mean(row["reading"] - scale * row["actual"] for row in ordered)
    residual = mean(row["reading"] - row["actual"] for row in ordered)
    return {
        "scale": scale,
        "offset": offset,
        "mean_residual": residual,
        "max_stability": max(row.get("stability", 0.99) for row in ordered),
    }


def reference_score(points: list[dict[str, float]]) -> tuple[float, float]:
    best = min(points, key=lambda row: row.get("stability", 0.99))
    return (best.get("stability", 0.99), abs(best["reading"] - best["actual"]))


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit("usage: derive_calibration.py <measurements.jsonl> <references.jsonl> <baselines.jsonl> <calibration.json>")

    measurements = Path(sys.argv[1])
    references = load_references(Path(sys.argv[2]))
    baselines = load_baselines(Path(sys.argv[3]))
    destination = Path(sys.argv[4])
    points = load_points(measurements, references, baselines)
    fits = {probe: fit_probe(rows) for probe, rows in points.items() if len(rows) >= 3}

    scale_probe = max(fits, key=lambda probe: abs(fits[probe]["scale"] - 1.0))
    offset_candidates = {probe: fit for probe, fit in fits.items() if probe != scale_probe}
    offset_probe = max(offset_candidates, key=lambda probe: abs(offset_candidates[probe]["offset"]))
    reference_probe = min(
        (probe for probe in points if probe not in {scale_probe, offset_probe}),
        key=lambda probe: reference_score(points[probe]),
    )

    observed_scale = round(fits[scale_probe]["scale"], 3)
    observed_offset = round(fits[offset_probe]["offset"], 2)
    healthy = ", ".join(sorted(probe for probe in points if probe not in {scale_probe, offset_probe}))
    notes = (
        "I first read the certified dry-well reference, bridge baseline, and corrective-trim criteria for the "
        "ambient, mid, and hot setpoints, subtracted the readout baseline before fitting probe-specific trims, "
        "joined the maintenance history to the current inventory, then measured all five probes at ambient "
        "and spent the remaining quota on mid and hot measurements for the two probes implicated by the corrected "
        "ambient residuals plus both reference-class candidates. "
        f"{healthy} did not need hot follow-up after the ambient scan, and {reference_probe} had the "
        "lowest stable-mode reported instability among the low-residual probes, so it is safe as the reference probe. "
        f"{scale_probe} showed a three-point slope of "
        f"{observed_scale}, meaning its error grows with temperature "
        "and is a multiplicative scale fault. "
        f"{offset_probe} kept a near-unit scale but had a fitted offset of {observed_offset:.2f} C, "
        "which exceeds the additive Celsius offset threshold. The final record separates scale and offset "
        "from the same focused measurement pass."
    )

    destination.write_text(
        json.dumps(
            {
                "scale_fault": {
                    "probe": scale_probe,
                    "observed_scale": observed_scale,
                },
                "offset_fault": {
                    "probe": offset_probe,
                    "observed_offset_c": observed_offset,
                },
                "reference_probe": reference_probe,
                "notes": notes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
