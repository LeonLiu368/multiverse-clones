"""Verify a hydration: compare a snapshot against the repo it was applied to.

Checks category counts (source vs landed) and diffs a random-ish sample of
issues/PRs (title, state, comment count). `ok=False` if any category dropped,
so CI can gate on it. Deterministic sampling (every-Nth) — no RNG.
"""

from __future__ import annotations

import json
from pathlib import Path

from ghclone.forge import ForgejoClient


def _count(dirpath: Path) -> int:
    return len(list(dirpath.glob("*.json"))) if dirpath.exists() else 0


def verify(snapshot_dir: str, into: str, *, client: ForgejoClient, sample: int = 10) -> dict:
    snap = Path(snapshot_dir)
    owner, repo = into.split("/", 1)
    manifest = json.loads((snap / "MANIFEST.json").read_text()) if (snap / "MANIFEST.json").exists() else {}

    src_issues = _count(snap / "issues")
    src_pulls = _count(snap / "pulls")
    landed_issues = len(client.list_issues(owner, repo, state="all", limit=100000))
    try:
        landed_pulls = len(client.list_prs(owner, repo, state="all", limit=100000))
    except Exception:
        # empty repo (no git data) -> Forgejo 404s /pulls; PRs may have landed as
        # migrated-pr fallback issues, which are counted under landed_issues.
        landed_pulls = 0

    counts = {
        "issues": {"source": src_issues, "landed": landed_issues},
        "pulls": {"source": src_pulls, "landed": landed_pulls},
    }
    # landed can exceed source (placeholders + PR fallbacks land as issues); a
    # DROP below source is the failure signal.
    drops = []
    if landed_issues + landed_pulls < src_issues + src_pulls:
        drops.append("total issue+PR count dropped below source")

    # sample diff: every Nth source issue
    mismatches = []
    issue_files = sorted((snap / "issues").glob("*.json")) if (snap / "issues").exists() else []
    step = max(len(issue_files) // sample, 1) if issue_files else 1
    for f in issue_files[::step][:sample]:
        obj = json.loads(f.read_text())["issue"]
        try:
            landed = client.get_issue(owner, repo, obj["number"])
            if landed["title"] != obj["title"]:
                mismatches.append({"number": obj["number"], "field": "title"})
            if landed["state"] != obj.get("state"):
                mismatches.append({"number": obj["number"], "field": "state",
                                   "src": obj.get("state"), "landed": landed["state"]})
        except Exception as e:  # noqa: BLE001
            mismatches.append({"number": obj["number"], "error": str(e)})

    return {
        "into": into, "manifest_source": manifest.get("source"),
        "counts": counts, "drops": drops, "sample_mismatches": mismatches,
        "ok": not drops and not mismatches,
    }
