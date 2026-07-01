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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import threading

from ..slice import parse_cutoff
from ..pipeline import discover as disc
from ..pipeline import generate as gen
from ..pipeline import spec as spc
from ..pipeline import validate
from . import publish as pub
from .jobs import Job, JobStore
from .pipelines import plan_task_from_run
from .sources import DEFAULT_T, PUBLISHABLE, SOURCES, source_summaries

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


@app.middleware("http")
async def _no_store(request, call_next):
    # local dev tool — never cache the UI assets, so edits always show on reload
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-store"
    return resp
store = JobStore(RUNS_DIR)
published = pub.PublishedRegistry(str(Path(RUNS_DIR) / "_published.json"))
candidates = disc.CandidateQueue(str(Path(RUNS_DIR) / "_candidates.json"))
TASKS_DIR = Path(RUNS_DIR) / "_tasks"
tasks_reg = pub.PublishedRegistry(str(Path(RUNS_DIR) / "_tasks.json"))   # same persisted-list shape


# ----------------------------------------------------------------- request bodies
class CaptureBody(BaseModel):
    source: str
    params: Dict[str, Any] = {}
    name: str = ""


class RenameBody(BaseModel):
    name: str


class PublishBody(BaseModel):
    image: str


# ----------------------------------------------------------------- sources / runs
@app.get("/api/sources")
def get_sources():
    return {"sources": source_summaries(), "default_t": DEFAULT_T}


@app.get("/api/sources/{source_id}/options/{param}")
def get_options(source_id: str, param: str, request: Request):
    """Discover selectable values for a param (Slack channels, Linear teams, GitHub repos in an
    org, …) so the UI can pre-populate checkboxes instead of making the user type names. Extra
    query params (e.g. ?org=abundant-ai) are passed through for dependent lookups. Hits live."""
    src = SOURCES.get(source_id)
    if not src or not src.options:
        raise HTTPException(404, "no options for this source")
    if not src.has_key():
        raise HTTPException(400, f"{src.env_key} not set in .env")
    try:
        return src.options(param, **dict(request.query_params))
    except Exception as e:  # noqa: BLE001 — surface upstream/credential errors cleanly
        raise HTTPException(400, f"{type(e).__name__}: {e}")


@app.get("/api/runs")
def get_runs():
    runs = store.list()
    for d in runs:
        j = store.get(d["id"])
        if j and j.status == "done":
            d["metadata"] = _run_metadata(j)
    return {"runs": runs}


@app.get("/api/runs/{job_id}")
def get_run(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such run")
    d = job.to_dict()
    rd = store.run_dir(job_id)
    d["artifacts"] = sorted(p.name for p in rd.iterdir()) if rd.exists() else []
    d["metadata"] = _run_metadata(job)
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

    name = body.name.strip() or f"{src.label} snapshot"
    job = store.submit("capture", src.id, body.params, _do, name=name)
    return job.to_dict()


# ----------------------------------------------------------------- rename / delete
@app.post("/api/runs/{job_id}/rename")
def rename_run(job_id: str, body: RenameBody):
    job = store.rename(job_id, body.name)
    if not job:
        raise HTTPException(404, "no such run")
    return job.to_dict()


@app.delete("/api/runs/{job_id}")
def delete_run(job_id: str):
    if not store.delete(job_id):
        raise HTTPException(404, "no such run")
    return {"deleted": job_id}


# ----------------------------------------------------------------- publish (bake + push to GHCR)
@app.get("/api/runs/{job_id}/publish/suggest")
def publish_suggest(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "no such run")
    return {"image": pub.suggest_image(job.source, job.name or job.source),
            "publishable": job.source in PUBLISHABLE,
            "metadata": _run_metadata(job)}


@app.post("/api/runs/{job_id}/publish")
def publish_run(job_id: str, body: PublishBody):
    job = store.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(400, "run not found or not finished")
    if job.source not in PUBLISHABLE:
        raise HTTPException(400, f"{job.source} is not publishable (needs a single bakeable overlay)")
    image = body.image.strip()
    if not image:
        raise HTTPException(400, "image ref required")
    store.set_published(job_id, {"status": "publishing", "image": image})

    def _bg():
        try:
            rec = pub.publish(job.source, str(store.run_dir(job_id)), image, job.report)
            rec.update({"status": "done", "source": job.source, "run_id": job_id,
                        "name": job.name, "metadata": _run_metadata(job)})
            published.add(rec)
            store.set_published(job_id, rec)
        except Exception as e:  # noqa: BLE001
            store.set_published(job_id, {"status": "error", "image": image, "error": str(e)[:500]})

    threading.Thread(target=_bg, daemon=True).start()
    return {"status": "publishing", "image": image}


@app.get("/api/published")
def get_published():
    return {"published": published.list()}


def _run_metadata(job: Job) -> Dict[str, Any]:
    """Cleanly displayable metadata for a run (channels, repos, timestamps, location, counts)."""
    r = job.report or {}
    rd = store.run_dir(job.id)
    md: Dict[str, Any] = {"as of": r.get("as_of"), "location": str(rd.resolve())}
    if r.get("channels"):
        md["channels"] = ", ".join(r["channels"])
    if r.get("since"):
        md["history"] = r["since"]
    if r.get("team"):
        md["team"] = r["team"]
    if r.get("org"):
        md["org"] = r["org"]
    if r.get("repo_names"):
        md["repos"] = ", ".join(r["repo_names"][:12]) + (" …" if len(r["repo_names"]) > 12 else "")
    if r.get("counts"):
        md.update({k: v for k, v in r["counts"].items()})
    for k in ("incident_records", "overview_signatures", "issues_kept", "issues_dropped", "comments_kept", "repos"):
        if r.get(k) is not None:
            md[k.replace("_", " ")] = r[k]
    return {k: v for k, v in md.items() if v is not None}


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


class SpecBody(BaseModel):
    run_ids: list[str]
    name: str = "incident/new-task"
    kind: str = "observability"
    incident_t: str = DEFAULT_T
    instruction: str = ""
    anchor_repo: str = ""
    anchor_commit: str = ""
    resolution_pr: str = ""
    verifier_kind: str = ""


@app.post("/api/tasks/spec")
def task_spec(body: SpecBody):
    """Assemble a runnable pipeline spec.json from picked runs + a code anchor. TODO fields
    (baked gateway tags, the SUT bundle, the verifier detail) are marked — fill them, then
    `python -m spoink.pipeline spec.json`. This is the dashboard -> pipeline seam."""
    slug = body.incident_t.replace(":", "").replace("-", "")[:13]
    surfaces = []
    for rid in body.run_ids:
        j = store.get(rid)
        if not j or j.status != "done":
            continue
        art = j.report.get("artifact") or SOURCES.get(j.source, None) and SOURCES[j.source].artifact
        surfaces.append({
            "source": j.source,
            "overlay": str((store.run_dir(rid) / art).resolve()) if art else str(store.run_dir(rid)),
            "gateway_image": f"ghcr.io/abundant-ai/{pub.DEFAULT_REPO.get(j.source, j.source + '-gateway')}:TODO-bake-{slug}",
        })
    vkind = body.verifier_kind or ("pytest_pr" if body.resolution_pr else
                                   "readback" if body.kind == "integration" else "module_check")
    verifier = {"kind": vkind}
    if vkind == "pytest_pr":
        verifier.update({"f2p": ["TODO: derive via spoink.pipeline.verifier.derive_pr_verifier"], "p2p": []})
    elif vkind == "module_check":
        verifier["grader_script"] = "TODO: path to a bespoke grader (e.g. configure_mappers smoke)"
    elif vkind == "readback":
        verifier["checks"] = [{"cmd": "TODO: a clone CLI read", "expect_substr": "TODO"}]
    spec = {
        "name": body.name, "kind": body.kind, "incident_t": body.incident_t,
        "instruction": body.instruction or "TODO: symptom-level prompt (name the tools, not the answer)",
        "surfaces": surfaces, "verifier": verifier,
        "anchor": ({"bundle": "TODO: git bundle sliced to the incident tip",
                    "commit": body.anchor_commit or "TODO: incident-tip sha",
                    "backend_subdir": "backend"} if body.anchor_repo else None),
        "source_repo": body.anchor_repo, "fixed_by_pr": body.resolution_pr,
    }
    todos = [f"surface[{i}].gateway_image — bake {s['source']} overlay into a gateway image"
             for i, s in enumerate(surfaces)]
    if spec["anchor"]:
        todos.append("anchor.bundle — produce a git bundle of the SUT sliced to the incident tip")
    todos.append(f"verifier ({vkind}) — fill in per the comments")
    return {"spec": spec, "todos": todos,
            "next": "save as spec.json, complete the TODOs, then: python -m spoink.pipeline spec.json --out generated-tasks/"}


# ================================================================= Task Creator
class DiscoverBody(BaseModel):
    feed: str = "github_revert"
    org: str = "abundant-ai"
    window_days: int = 120
    max_repos: int = 40
    max_candidates: int = 60


class AttachBody(BaseModel):
    snapshots: Dict[str, str] = {}          # source -> run_id


class CaptureBatchBody(BaseModel):
    name: str = ""                          # batch label; sources default to the candidate's required_data


@app.post("/api/candidates/discover")
def candidates_discover(body: DiscoverBody):
    """Run a discovery feed over the live upstreams and merge new incidents into the queue."""
    if body.feed not in disc.FEEDS:
        raise HTTPException(404, f"unknown feed {body.feed!r}; have {sorted(disc.FEEDS)}")
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        raise HTTPException(400, "GITHUB_TOKEN not set in .env")
    try:
        found = disc.discover(body.feed, tok, org=body.org, window_days=body.window_days,
                              max_repos=body.max_repos, max_candidates=body.max_candidates)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"discovery failed: {e}")
    added = candidates.merge(found)
    return {"discovered": len(found), "added": added, "candidates": candidates.list()}


@app.get("/api/candidates")
def candidates_list():
    return {"candidates": candidates.list()}


@app.delete("/api/candidates/{cid}")
def candidates_delete(cid: str):
    if not candidates.remove(cid):
        raise HTTPException(404, "no such candidate")
    return {"deleted": cid}


@app.post("/api/candidates/{cid}/attach")
def candidates_attach(cid: str, body: AttachBody):
    """Attach existing (done) runs to a candidate's required surfaces."""
    c = candidates.get(cid)
    if not c:
        raise HTTPException(404, "no such candidate")
    snaps = dict(c.get("snapshots") or {})
    for source, rid in body.snapshots.items():
        j = store.get(rid)
        if not j or j.status != "done":
            raise HTTPException(400, f"run {rid} not found or not done")
        snaps[source] = rid
    status = "attached" if snaps else c.get("status", "new")
    return {"candidate": candidates.update(cid, snapshots=snaps, status=status)}


@app.post("/api/candidates/{cid}/capture")
def candidates_capture(cid: str, body: CaptureBatchBody):
    """Batch-capture the candidate's required surfaces at its incident time T. Reuses the capture
    jobs; each source's params come from the candidate's required_data (so as_of == T)."""
    c = candidates.get(cid)
    if not c:
        raise HTTPException(404, "no such candidate")
    batch = body.name.strip() or (c.get("title", cid)[:40])
    started: Dict[str, str] = {}
    skipped: Dict[str, str] = {}
    for source, params in (c.get("required_data") or {}).items():
        src = SOURCES.get(source)
        if not src or not src.has_key():
            skipped[source] = "no source/key"
            continue

        def _do(job: Job, _src=src, _params=params) -> Dict[str, Any]:
            return _src.capture(str(store.run_dir(job.id)), _params)

        job = store.submit("capture", src.id, params, _do, name=f"{batch} · {source}")
        started[source] = job.id
    snaps = {**(c.get("snapshots") or {}), **started}
    candidates.update(cid, snapshots=snaps, status="capturing")
    return {"candidate": candidates.get(cid), "started": started, "skipped": skipped}


@app.post("/api/candidates/{cid}/generate")
def candidates_generate(cid: str):
    """Process the candidate into a Harbor-format task dir under runs/_tasks/. Attached snapshots
    must be done. Emits the preview-500s shape (environment/ + task.toml + tests/ + solution/)."""
    c = candidates.get(cid)
    if not c:
        raise HTTPException(404, "no such candidate")
    attached = []
    for source, rid in (c.get("snapshots") or {}).items():
        j = store.get(rid)
        if not j or j.status != "done":
            continue
        art = j.report.get("artifact") or (SOURCES.get(source) and SOURCES[source].artifact)
        attached.append({"source": source,
                         "overlay": str((store.run_dir(rid) / art).resolve()) if art else str(store.run_dir(rid))})
    if not attached:
        raise HTTPException(400, "no done snapshots attached — capture or attach first")
    gateway_for = {s: f"ghcr.io/abundant-ai/{pub.DEFAULT_REPO.get(s, s + '-gateway')}:TODO-bake"
                   for s in (c.get("required_data") or {})}
    spec = spc.spec_from_candidate(c, attached, gateway_for)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    out = TASKS_DIR / spec.slug()
    res = gen.generate_task(spec, str(out))
    # validation gates (clone-task-builder non-negotiables): contract, code-cut, leakage, verifier
    report = validate.validate_task(
        res["task_dir"], bundle=str(Path(res["task_dir"]) / "environment" / "codebase.bundle"),
        resolution=c.get("resolution", {}),
        # github leakage is governed by code_cut + the forge's apply --as-of T, not the text grep
        overlays=[r["overlay"] for r in attached if r["source"] != "github"],
        changed_files=spec.changed_files, title=c.get("title", ""),
        verifier_kind=spec.verifier.kind, f2p=spec.verifier.f2p).to_dict()
    rec = {"image": spec.name, "id": cid, "name": spec.name, "task_dir": res["task_dir"],
           "surfaces": res["surfaces"], "verifier": res["verifier"],
           "resolution": c.get("resolution", {}), "created_at": _now_iso(),
           "validation": report}
    tasks_reg.add(rec)
    candidates.update(cid, status="generated" if report["accepted"] else "generated-rejected")
    return {"task": rec}


@app.get("/api/tasks")
def tasks_list():
    return {"tasks": tasks_reg.list()}


@app.get("/api/tasks/{cid}/source")
def task_source(cid: str):
    """The generated task's source tree (relative path -> file text) for the Tasks browser."""
    rec = next((t for t in tasks_reg.list() if t.get("id") == cid), None)
    if not rec:
        raise HTTPException(404, "no such task")
    root = Path(rec["task_dir"])
    files = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.stat().st_size < 200_000:
            files[str(p.relative_to(root))] = p.read_text(errors="replace")
    return {"task_dir": str(root), "files": files}


def _now_iso() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
