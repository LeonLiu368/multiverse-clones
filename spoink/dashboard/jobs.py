"""Jobs — capture/slice runs, persisted under a runs/ dir and executed on a small thread
pool (capture can take minutes). Each run is a self-describing directory:

    runs/<job_id>/
        job.json        # the Job record (status, params, timings, report summary)
        <artifact>      # slack-export/ | state.json | logfire.json (+ sliced @T variants)

Survives restarts: the store rehydrates from runs/*/job.json on construction.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _now() -> float:
    return time.time()


@dataclass
class Job:
    id: str
    kind: str                       # "capture" | "slice"
    source: str                     # source id (slack/linear/logfire)
    params: Dict[str, Any] = field(default_factory=dict)
    status: str = "queued"          # queued | running | done | error
    created: float = field(default_factory=_now)
    started: Optional[float] = None
    finished: Optional[float] = None
    report: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    parent: Optional[str] = None    # for slice jobs: the capture run they sliced
    label: str = ""                 # human label (e.g. "@ 2026-06-25T00:34:00Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class JobStore:
    def __init__(self, runs_dir: str, max_workers: int = 3):
        self.root = Path(runs_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="spoink-job")
        self._rehydrate()

    # ----- persistence
    def _rehydrate(self) -> None:
        for jf in sorted(self.root.glob("*/job.json")):
            try:
                d = json.loads(jf.read_text())
                # a job left "running" across a restart is stale -> mark error
                if d.get("status") == "running":
                    d["status"] = "error"
                    d["error"] = "interrupted (server restart)"
                self._jobs[d["id"]] = Job(**{k: d.get(k) for k in Job.__dataclass_fields__})
            except Exception:
                continue

    def _persist(self, job: Job) -> None:
        d = self.root / job.id
        d.mkdir(parents=True, exist_ok=True)
        (d / "job.json").write_text(json.dumps(job.to_dict(), indent=2, default=str))

    def run_dir(self, job_id: str) -> Path:
        return self.root / job_id

    # ----- queries
    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [j.to_dict() for j in sorted(self._jobs.values(), key=lambda j: -j.created)]

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    # ----- submit
    def submit(self, kind: str, source: str, params: Dict[str, Any],
               fn: Callable[[Job], Dict[str, Any]], parent: Optional[str] = None,
               label: str = "") -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, source=source, params=params,
                  parent=parent, label=label)
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        self._pool.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[Job], Dict[str, Any]]) -> None:
        job.status = "running"
        job.started = _now()
        self._persist(job)
        try:
            job.report = fn(job) or {}
            job.status = "done"
        except Exception as e:  # noqa: BLE001 — surface any capture/slice failure to the UI
            job.status = "error"
            job.error = f"{type(e).__name__}: {e}"
            job.report = {"traceback": traceback.format_exc()[-2000:]}
        finally:
            job.finished = _now()
            self._persist(job)
