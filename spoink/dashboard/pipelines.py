"""Task-creation pipeline (preview / extension point).

The endgame for the dashboard: turn a captured-and-sliced incident (a set of overlays at T,
plus a code anchor) into a runnable agent-eval task — the same shape as
experiments/oddish-incident/tasks/preview-500s (a buggy SUT checkout + time-aligned evidence
sidecars + a verifier).

For now this returns a PLAN describing what such a task would bundle from a given run, so the
UI can show the path from "captured data" to "task" without committing to scaffolding yet.
Wire the real generator here when we're ready (it will: pick the code anchor commit, bake the
overlays into per-incident gateway images, and emit the task dir + manifest)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .sources import SOURCES


def plan_task_from_run(job: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
    src = SOURCES.get(job.get("source", ""))
    artifacts = sorted(p.name for p in run_dir.iterdir()) if run_dir.exists() else []
    cutoff = job.get("params", {}).get("until") or job.get("params", {}).get("cutoff") or job.get("label")
    return {
        "status": "preview",
        "run_id": job.get("id"),
        "source": job.get("source"),
        "cutoff_T": cutoff,
        "artifacts": artifacts,
        "would_bundle": {
            "evidence_sidecar": (src.view_app if src else None),
            "gateway_bake": f"bake {artifacts} into a {job.get('source')}-gateway:<incident> image",
            "code_anchor": "TODO: pick the SUT repo + commit at T (e.g. oddish @ incident tip)",
            "verifier": "TODO: derive from the resolution PR (pr_to_task / configure_mappers-style check)",
        },
        "note": "task generation is not wired yet — this is the plan a future pipeline would execute.",
    }
