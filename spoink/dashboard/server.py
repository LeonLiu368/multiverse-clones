"""spoink dashboard — a capture/slice control plane.

Kick off capture jobs against the upstreams (keys from .env), time-align them to an incident
cutoff T, and hand the produced overlays to seed-dashboard for viewing. One HTTP API; a thin
static frontend is the only client.

    python -m spoink.dashboard            # serves http://localhost:8787

Env:
  SPOINK_RUNS_DIR        where runs/ live (default ./runs)
  SEED_DASHBOARD_URL     seed-dashboard backend for the "View" action (default http://localhost:8000)
  SPOINK_DASHBOARD_PORT  default 8787
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..slice import parse_cutoff
from .jobs import Job, JobStore
from .pipelines import plan_task_from_run
from .sources import DEFAULT_T, SOURCES, source_summaries

# Load .env so the source credentials (SLACK_USER_TOKEN / LINEAR_API_KEY / LOGFIRE_READ_TOKEN)
# are present — values stay in the process, never returned over the API.
if not os.environ.get("SPOINK_SKIP_DOTENV"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # python-dotenv optional; env may already be exported
        pass

RUNS_DIR = os.environ.get("SPOINK_RUNS_DIR", "runs")
SEED_DASHBOARD_URL = os.environ.get("SEED_DASHBOARD_URL", "http://localhost:8000").rstrip("/")
HERE = Path(__file__).resolve().parent

app = FastAPI(title="spoink dashboard")
store = JobStore(RUNS_DIR)


# ----------------------------------------------------------------- request bodies
class CaptureBody(BaseModel):
    source: str
    params: Dict[str, Any] = {}


class SliceBody(BaseModel):
    run_id: str
    cutoff: str = DEFAULT_T            # ISO/epoch/'YYYY-MM-DD HH:MM'
    tz: Optional[str] = None


# ----------------------------------------------------------------- sources / runs
@app.get("/api/sources")
def get_sources():
    return {"sources": source_summaries(), "default_t": DEFAULT_T}


@app.get("/api/sources/{source_id}/options/{param}")
def get_options(source_id: str, param: str):
    """Discover selectable values for a param (Slack channels, Linear teams, …) so the UI can
    pre-populate checkboxes instead of making the user type names. Hits the upstream live."""
    src = SOURCES.get(source_id)
    if not src or not src.options:
        raise HTTPException(404, "no options for this source")
    if not src.has_key():
        raise HTTPException(400, f"{src.env_key} not set in .env")
    try:
        return src.options(param)
    except Exception as e:  # noqa: BLE001 — surface upstream/credential errors cleanly
        raise HTTPException(400, f"{type(e).__name__}: {e}")


@app.get("/api/runs")
def get_runs():
    return {"runs": store.list()}


@app.get("/api/runs/{job_id}")
def get_run(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such run")
    d = job.to_dict()
    rd = store.run_dir(job_id)
    d["artifacts"] = sorted(p.name for p in rd.iterdir()) if rd.exists() else []
    return d


# ----------------------------------------------------------------- capture
@app.post("/api/capture")
def capture(body: CaptureBody):
    src = SOURCES.get(body.source)
    if not src:
        raise HTTPException(404, f"unknown source {body.source!r}")
    if not src.has_key():
        raise HTTPException(400, f"{src.env_key} not set in .env")

    def _do(job: Job) -> Dict[str, Any]:
        return src.capture(str(store.run_dir(job.id)), body.params)

    label = body.params.get("until") or body.params.get("latest") or ""
    job = store.submit("capture", src.id, body.params, _do, label=f"capture {src.label} {label}".strip())
    return job.to_dict()


# ----------------------------------------------------------------- slice (time-align to T)
@app.post("/api/slice")
def slice_run(body: SliceBody):
    parent = store.get(body.run_id)
    if not parent or parent.status != "done":
        raise HTTPException(400, "parent run not found or not finished")
    src = SOURCES.get(parent.source)
    if not src or not src.can_slice or not src.slice:
        raise HTTPException(400, f"{parent.source} does not support slicing (it is captured as-of-T)")
    try:
        cutoff = parse_cutoff(body.cutoff, body.tz)
    except SystemExit as e:
        raise HTTPException(400, str(e))

    # slice writes its @T artifact into the SAME run dir as the parent capture
    pdir = str(store.run_dir(body.run_id))
    artifact = parent.report.get("artifact", src.artifact)

    def _do(job: Job) -> Dict[str, Any]:
        # mirror the parent's artifacts into this job dir for a self-contained sliced run
        res = src.slice(pdir, artifact, cutoff)
        # copy the produced @T file into this slice-job's dir so it stands alone
        produced = res.get("artifact")
        if produced and (Path(pdir) / produced).exists():
            dest = store.run_dir(job.id) / produced
            dest.parent.mkdir(parents=True, exist_ok=True)
            if (Path(pdir) / produced).is_dir():
                import shutil
                shutil.copytree(Path(pdir) / produced, dest, dirs_exist_ok=True)
            else:
                dest.write_bytes((Path(pdir) / produced).read_bytes())
        return res

    job = store.submit("slice", src.id, {"cutoff": body.cutoff, "tz": body.tz}, _do,
                       parent=body.run_id, label=f"slice @ {body.cutoff}")
    return job.to_dict()


# ----------------------------------------------------------------- view in seed-dashboard
@app.post("/api/runs/{job_id}/view")
def view(job_id: str):
    job = store.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(400, "run not found or not finished")
    src = SOURCES.get(job.source)
    if not src or not src.view_app:
        raise HTTPException(400, "source has no seed-dashboard viewer")
    artifact = job.report.get("artifact")
    overlay_path = str((store.run_dir(job_id) / artifact).resolve()) if artifact else None

    # Try to load the overlay into seed-dashboard via its adapter API; fall back to a manual hint.
    loaded = None
    err = None
    try:
        bases = _seed_get(f"/api/{src.view_app}/bases")
        base_id = (bases[0]["id"] if isinstance(bases, list) and bases else None)
        loaded = _seed_post(f"/api/{src.view_app}/load",
                            {"base_id": base_id, "overlay_path": overlay_path})
    except Exception as e:  # noqa: BLE001 — seed-dashboard may be offline; degrade gracefully
        err = str(e)
    return {
        "view_app": src.view_app,
        "overlay_path": overlay_path,
        "seed_dashboard_url": SEED_DASHBOARD_URL,
        "loaded": loaded,
        "hint": None if loaded else
        f"start seed-dashboard (./run.sh), open it, and Load this overlay into the "
        f"'{src.view_app}' app: {overlay_path}",
        "error": err,
    }


# ----------------------------------------------------------------- task pipeline (preview)
@app.get("/api/runs/{job_id}/task_plan")
def task_plan(job_id: str):
    """Future task-creation pipeline — for now returns a PLAN (what a task would bundle)."""
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such run")
    return plan_task_from_run(job.to_dict(), store.run_dir(job_id))


# ----------------------------------------------------------------- static frontend
@app.get("/")
def index():
    return FileResponse(str(HERE / "static" / "index.html"))


app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


# ----------------------------------------------------------------- seed-dashboard helpers
def _seed_get(path: str):
    req = urllib.request.Request(SEED_DASHBOARD_URL + path)
    with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 (local dev service)
        return json.loads(r.read())


def _seed_post(path: str, body: dict):
    req = urllib.request.Request(SEED_DASHBOARD_URL + path, method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return json.loads(r.read())


def main(argv=None) -> int:
    import uvicorn
    port = int(os.environ.get("SPOINK_DASHBOARD_PORT", "8787"))
    print(f"[spoink-dashboard] runs={RUNS_DIR}  seed-dashboard={SEED_DASHBOARD_URL}", flush=True)
    print(f"[spoink-dashboard] open http://localhost:{port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
