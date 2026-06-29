"""Seeded GitHub Actions overlay.

Forgejo's Actions API does not expose GitHub-compatible run/job/step/log endpoints
(`/actions/runs/*`, `/actions/jobs/*/logs` all 404; the web log route needs a CSRF
session), and the live act_runner is non-deterministic. To give `gh run`/`gh workflow`/
`gh pr checks` a GitHub-exact, fully deterministic surface for benchmark worlds, this
module serves Actions data from a per-world JSON seed instead.

The seed path is taken from `GH_ACTIONS_SEED` / `GHC_ACTIONS_SEED` (or a token-file-style
fallback for the isolated multi-container layout). When a seed exists for a repo, the CLI
renders runs/jobs/steps/logs/check-runs from it; otherwise it falls back to the live forge.

Seed shape (everything except repo + a run id/number is optional and defaulted):

    {
      "repos": {
        "acme/payments": {
          "workflows": [{"id": 161335, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"}],
          "runs": [{
            "id": 4242, "number": 42, "workflow": "CI", "title": "fix: capture race",
            "event": "push", "status": "completed", "conclusion": "failure",
            "branch": "main", "sha": "abc1234...", "actor": "octo-dev",
            "created_at": "...", "started_at": "...", "updated_at": "...",
            "jobs": [{
              "id": 9002, "name": "test", "conclusion": "failure",
              "started_at": "...", "completed_at": "...",
              "steps": [{"name": "Run tests", "conclusion": "failure", "log": "FAIL ...\n"}]
            }]
          }]
        }
      }
    }
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# gh's run/job/step status glyphs (pkg/cmd/run/shared.Symbol): ✓ success, X failure,
# - skipped/cancelled/neutral, * in-progress. We emit the plain glyphs (no color) so
# piped output is byte-identical to `gh` under a pipe.
ICON_SUCCESS = "✓"
ICON_FAILURE = "X"
ICON_SKIPPED = "-"
ICON_PROGRESS = "*"

# gh categorizes a check's state into one of these buckets (gh pr checks --json bucket).
_FAIL_CONCL = {"failure", "timed_out", "startup_failure", "action_required"}
_SKIP_CONCL = {"skipped", "neutral", "stale"}


def _icon(status: str, conclusion: str | None) -> str:
    """Mirror gh's shared.Symbol: keyed on completed-vs-not, then conclusion."""
    if status == "completed":
        if conclusion == "success":
            return ICON_SUCCESS
        if conclusion == "cancelled" or conclusion in _SKIP_CONCL:
            return ICON_SKIPPED
        return ICON_FAILURE
    return ICON_PROGRESS


def _bucket(status: str, conclusion: str | None) -> str:
    """gh pr checks bucket: pass | fail | pending | skipping | cancel."""
    if status != "completed":
        return "pending"
    if conclusion == "success":
        return "pass"
    if conclusion == "cancelled":
        return "cancel"
    if conclusion in _SKIP_CONCL:
        return "skipping"
    return "fail"


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration(start: Any, end: Any) -> str:
    a, b = _parse_ts(start), _parse_ts(end)
    if not a or not b:
        return "0s"
    secs = max(0, int((b - a).total_seconds()))
    # Go's time.Duration.String() shape, which gh prints verbatim (e.g. 32s, 1m18s, 1h2m3s).
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m{secs % 60}s"
    return f"{secs // 3600}h{(secs % 3600) // 60}m{secs % 60}s"


class ActionsOverlay:
    """Read-only view over the seeded Actions data, normalized to GitHub shapes."""

    def __init__(self, data: dict[str, Any], source: str = ""):
        self._repos: dict[str, Any] = data.get("repos", {}) if isinstance(data, dict) else {}
        self.source = source

    # ---- loading -----------------------------------------------------------------
    @classmethod
    def seed_path(cls) -> str | None:
        explicit = os.getenv("GH_ACTIONS_SEED") or os.getenv("GHC_ACTIONS_SEED")
        candidates = [explicit, "/run/secrets/actions-seed.json", "/shared/actions-seed.json", "/etc/ghc/actions-seed.json"]
        for cand in candidates:
            if cand and Path(cand).exists():
                return cand
        return None

    @classmethod
    def load(cls) -> "ActionsOverlay | None":
        path = cls.seed_path()
        if not path:
            return None
        try:
            return cls(json.loads(Path(path).read_text(encoding="utf-8")), source=path)
        except (json.JSONDecodeError, OSError):
            return None

    # ---- queries -----------------------------------------------------------------
    def has(self, owner: str, repo: str) -> bool:
        return f"{owner}/{repo}" in self._repos

    def _repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._repos.get(f"{owner}/{repo}", {})

    def workflows(self, owner: str, repo: str) -> list[dict[str, Any]]:
        out = []
        for index, wf in enumerate(self._repo(owner, repo).get("workflows", [])):
            out.append({
                "id": wf.get("id", index + 1),
                "name": wf.get("name") or Path(wf.get("path", "workflow.yml")).stem,
                "path": wf.get("path", f".github/workflows/{wf.get('name', 'ci')}.yml"),
                "state": wf.get("state", "active"),
            })
        return out

    def runs(self, owner: str, repo: str) -> list[dict[str, Any]]:
        runs = [self._normalize_run(r) for r in self._repo(owner, repo).get("runs", [])]
        return sorted(runs, key=lambda r: r["run_number"], reverse=True)

    def run(self, owner: str, repo: str, ref: int | str | None) -> dict[str, Any] | None:
        runs = self.runs(owner, repo)
        if ref is None:
            return runs[0] if runs else None
        return next((r for r in runs if str(r["run_number"]) == str(ref) or str(r["id"]) == str(ref)), None)

    def checks_for_ref(self, owner: str, repo: str, *, branch: str | None = None, sha: str | None = None) -> list[dict[str, Any]]:
        """Check runs (one per job) for a PR's head — match the most recent run on the branch/sha."""
        runs = self.runs(owner, repo)
        match = None
        for r in runs:
            if sha and r["head_sha"].startswith(str(sha)[:7]):
                match = r
                break
            if branch and r["head_branch"] == branch:
                match = r
                break
        if not match and runs:
            match = runs[0]
        if not match:
            return []
        checks = []
        for job in match["jobs"]:
            status, conclusion = job["status"], job["conclusion"]
            checks.append({
                "name": job["name"],
                "workflow": match["name"],
                "status": status,
                "conclusion": conclusion,
                "state": (conclusion or status or "").upper(),
                "bucket": _bucket(status, conclusion),
                "elapsed": _duration(job.get("started_at"), job.get("completed_at")),
                "started_at": job.get("started_at", ""),
                "completed_at": job.get("completed_at", ""),
                "event": match["event"],
                "description": job.get("description", ""),
                "required": bool(job.get("required", False)),
                "link": job.get("url") or match["url"],
                "url": job.get("url") or match["url"],
                "icon": _icon(status, conclusion),
            })
        return checks

    # ---- normalization -----------------------------------------------------------
    def _normalize_run(self, raw: dict[str, Any]) -> dict[str, Any]:
        jobs = [self._normalize_job(j, i) for i, j in enumerate(raw.get("jobs", []))]
        status = raw.get("status") or ("completed" if all(j["status"] == "completed" for j in jobs) and jobs else "in_progress")
        conclusion = raw.get("conclusion")
        if conclusion is None and status == "completed":
            conclusion = "failure" if any(j["conclusion"] == "failure" for j in jobs) else "success"
        number = raw.get("number", raw.get("run_number", raw.get("id", 1)))
        return {
            "id": raw.get("id", number),
            "run_number": number,
            "name": raw.get("workflow") or raw.get("name") or "CI",
            "workflow_id": raw.get("workflow_id", number),
            "display_title": raw.get("title") or raw.get("display_title") or raw.get("head_commit", ""),
            "event": raw.get("event", "push"),
            "status": status,
            "conclusion": conclusion,
            "head_branch": raw.get("branch") or raw.get("head_branch") or "main",
            "head_sha": str(raw.get("sha") or raw.get("head_sha") or ""),
            "actor": raw.get("actor", "ghc-admin"),
            "created_at": raw.get("created_at", ""),
            "run_started_at": raw.get("started_at") or raw.get("run_started_at") or raw.get("created_at", ""),
            "updated_at": raw.get("updated_at", ""),
            "url": raw.get("url", ""),
            "annotations": raw.get("annotations", []),
            "jobs": jobs,
        }

    def _normalize_job(self, raw: dict[str, Any], index: int) -> dict[str, Any]:
        steps = [self._normalize_step(s, i) for i, s in enumerate(raw.get("steps", []))]
        status = raw.get("status") or ("completed" if all(s["status"] == "completed" for s in steps) or not steps else "in_progress")
        conclusion = raw.get("conclusion")
        if conclusion is None and status == "completed":
            conclusion = "failure" if any(s["conclusion"] == "failure" for s in steps) else "success"
        return {
            "id": raw.get("id", index),
            "name": raw.get("name") or f"job-{index}",
            "status": status,
            "conclusion": conclusion,
            "started_at": raw.get("started_at", ""),
            "completed_at": raw.get("completed_at", ""),
            "url": raw.get("url", ""),
            "required": bool(raw.get("required", False)),
            "description": raw.get("description", ""),
            "steps": steps,
        }

    def _normalize_step(self, raw: dict[str, Any], index: int) -> dict[str, Any]:
        return {
            "number": raw.get("number", index + 1),
            "name": raw.get("name") or f"step {index + 1}",
            "status": raw.get("status", "completed"),
            "conclusion": raw.get("conclusion", "success"),
            "log": raw.get("log", ""),
        }


def run_duration(run: dict[str, Any]) -> str:
    return _duration(run.get("run_started_at") or run.get("created_at"), run.get("updated_at"))


def job_duration(job: dict[str, Any]) -> str:
    return _duration(job.get("started_at"), job.get("completed_at"))


def status_icon(status: str, conclusion: str | None) -> str:
    return _icon(status, conclusion)
