# spoink dashboard — capture / slice control plane

A small web control plane over spoink's capture + slice modules. Kick off captures against the
upstreams (credentials from `.env`), time-align them to an incident cutoff **T**, and hand the
produced overlays to **seed-dashboard** for viewing. One FastAPI backend; a no-build static
frontend is the only client.

```bash
pip install -e ".[dashboard]"          # fastapi + uvicorn + python-dotenv
python -m spoink.dashboard              # http://localhost:8787
```

**GitHub capture** additionally needs gh-cli-clone importable in *this* env (it drives
`ghclone snapshot`); the other sources capture in-process. Install it once:

```bash
pip install -e <multiverse-clones>/clones/gh-cli-clone   # provides `ghclone` / `ghc-hydrate`
```

The dashboard auto-resolves it (`$GHC_HYDRATE_BIN` → a `ghc-hydrate` on PATH → `python -m
ghclone.cli.admin`). Publishing a GitHub run also needs the `ghc-service` image present
(`scripts/images.sh build` in gh-cli-clone, or a GHCR pull) + a GHCR login for the push.

## What it does

- **Sources** (`SLACK_USER_TOKEN`, `LINEAR_API_KEY`, `LOGFIRE_READ_TOKEN`) are auto-detected from
  `.env`; the UI shows which keys are present (the *value* is never sent over the API).
- **Capture** runs the real `spoink.{slack,linear,logfire}_export` flow as a background job into
  `runs/<id>/` (artifact + `report.json` + `job.json`). Jobs survive restarts.
- **Slice @T** time-aligns a captured artifact to the incident cutoff (`slice_export` for Slack,
  `slice_tracker` for Linear). Logfire is captured *as-of-T* directly via its `until` param, so it
  isn't sliced.
- **View** loads the produced overlay into seed-dashboard via its adapter API
  (`/api/{app}/load`) and opens the viewer; if seed-dashboard is offline it shows the overlay path
  to load manually.

The central workflow: set **T** (defaults to the canonical incident `2026-06-25T00:34:00Z`) →
capture each source aligned to T → slice Slack/Linear to T → view each overlay.

## Layout

| file | role |
|---|---|
| `sources.py` | registry: per-source `capture()`/`slice()` wrapping the export modules + param schema + viewer app |
| `jobs.py` | persisted run store + thread-pool runner (`runs/<id>/`) |
| `server.py` | FastAPI: `/api/sources`, `/api/capture`, `/api/slice`, `/api/runs[/{id}]`, `/api/runs/{id}/view` |
| `static/` | vanilla-JS control panel |
| `pipelines.py` | **future** task-creation pipeline (captured+sliced incident @ T → a task dir) — currently returns a plan |

## Env

| var | default | meaning |
|---|---|---|
| `SPOINK_RUNS_DIR` | `runs` | where run artifacts live |
| `SEED_DASHBOARD_URL` | `http://localhost:8000` | seed-dashboard backend for the View action |
| `SPOINK_DASHBOARD_PORT` | `8787` | server port |
| `SPOINK_SKIP_DOTENV` | — | set to skip `.env` loading (env already exported / tests) |

## Roadmap

`pipelines.py` is the seam for the **task-creation pipeline**: turn a captured-and-sliced incident
(overlays at T + a code anchor commit + the resolution PR) into a runnable task like
`experiments/oddish-incident/tasks/preview-500s` — bake the overlays into per-incident gateway
images, vendor the SUT at the incident tip, and emit the task dir + manifest.
