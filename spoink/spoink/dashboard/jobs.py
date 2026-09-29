"""Jobs — capture runs, persisted under a runs/ dir and executed on a small thread pool
(capture can take minutes). Each run is a self-describing directory:

    runs/<job_id>/
        job.json        # the Job record (name, status, params, timings, report, progress)
        <artifact>      # slack-export/ | state.json | logfire.json | snapshots/ …

Survives restarts: the store rehydrates from runs/*/job.json on construction. The store also
tracks a rolling per-source duration history so running jobs can show a time estimate.
"""
from __future__ import annotations

import json
import shutil
import statistics
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
    kind: str                       # "capture"
    source: str                     # source id (slack/linear/logfire/github)
    params: Dict[str, Any] = field(default_factory=dict)
    status: str = "queued"          # queued | running | done | error
    created: float = field(default_factory=_now)
    started: Optional[float] = None
    finished: Optional[float] = None
    report: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    name: str = ""                  # renamable display name
    progress: Dict[str, Any] = field(default_factory=dict)   # {step, pct}
    published: Dict[str, Any] = field(default_factory=dict)  # {image, pushed_at} once published

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class JobStore:
    def __init__(self, runs_dir: str, max_workers: int = 3):
        self.root = Path(runs_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, Job] = {}
        self._durations: Dict[str, List[float]] = {}   # source -> recent run durations (s)
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="spoink-job")
        self._rehydrate()

    # ----- persistence
    def _rehydrate(self) -> None:
        for jf in sorted(self.root.glob("*/job.json")):
            try:
                d = json.loads(jf.read_text())
                if d.get("status") == "running":          # stale across a restart
                    d["status"] = "error"
                    d["error"] = "interrupted (server restart)"
                job = Job(**{k: d.get(k) for k in Job.__dataclass_fields__})
                self._jobs[job.id] = job
                if job.status == "done" and job.started and job.finished:
                    self._record_duration(job.source, job.finished - job.started)
            except Exception:
                continue

    def _persist(self, job: Job) -> None:
        d = self.root / job.id
        d.mkdir(parents=True, exist_ok=True)
        (d / "job.json").write_text(json.dumps(job.to_dict(), indent=2, default=str))

    def run_dir(self, job_id: str) -> Path:
        return self.root / job_id

    # ----- duration / ETA
    def _record_duration(self, source: str, secs: float) -> None:
        h = self._durations.setdefault(source, [])
        h.append(secs)
        del h[:-12]                                        # keep the last 12

    def eta(self, source: str) -> Optional[float]:
        h = self._durations.get(source)
        return statistics.median(h) if h else None

    # ----- queries
    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for j in sorted(self._jobs.values(), key=lambda j: -j.created):
                d = j.to_dict()
                d["eta"] = self.eta(j.source)
                out.append(d)
            return out

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    # ----- mutations
    def rename(self, job_id: str, name: str) -> Optional[Job]:
        job = self._jobs.get(job_id)
        if not job:
            return None
        job.name = name.strip()[:80]
        self._persist(job)
        return job

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if not job:
            return False
        shutil.rmtree(self.run_dir(job_id), ignore_errors=True)
        return True

    def set_published(self, job_id: str, info: Dict[str, Any]) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.published = info
            self._persist(job)

    # ----- submit
    def submit(self, kind: str, source: str, params: Dict[str, Any],
               fn: Callable[[Job], Dict[str, Any]], name: str = "") -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, source=source, params=params, name=name)
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
        except Exception as e:  # noqa: BLE001 — surface any capture failure to the UI
            job.status = "error"
            job.error = f"{type(e).__name__}: {e}"
            job.report = {"traceback": traceback.format_exc()[-2000:]}
        finally:
            job.finished = _now()
            if job.status == "done" and job.started:
                self._record_duration(job.source, job.finished - job.started)
            self._persist(job)
