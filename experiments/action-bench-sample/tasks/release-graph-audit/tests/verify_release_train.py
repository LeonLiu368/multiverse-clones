#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("TASK_APP_DIR", "/app"))
OUT_DIR = Path(os.environ.get("VERIFIER_LOG_DIR", "/logs/verifier"))
REPORT = APP_DIR / "release_handoff.json"
AUDIT = Path(os.environ.get("RELEASECTL_AUDIT_PATH", "/var/lib/releasectl/audit.jsonl"))
TOOL = Path("/usr/local/bin/releasectl")

SCHEMA_POINTS = 10.0
BLOCKER_SET_POINTS = 40.0
EXTRA_BLOCKER_PENALTY = 4.0
ORDER_MEMBERSHIP_POINTS = 5.0
ORDER_DEPENDENCY_POINTS = 15.0
EVIDENCE_POINTS = 20.0
HANDOFF_NOTE_POINTS = 6.0
TOOL_SURFACE_POINTS = 6.0
HANDOFF_NOTE_MIN_CHARS = 250

# Hard caps describe contract failures rather than weighted rubric preferences.
CAP_UNSUBMITTED = 42.0
CAP_MISSING_REQUIRED_DISCOVERY = 40.0
CAP_MISSING_DETAIL_INSPECTION = 70.0
CAP_MISSING_EVIDENCE_SURFACE = 65.0
CAP_MISSING_DEPENDENCY_SURFACE = 40.0
CAP_MISSING_TRUE_BLOCKER = 40.0
CAP_EXTRA_NON_BLOCKERS = 60.0
CAP_DEPENDENCY_ORDER_ERROR = 40.0
CAP_BROKEN_TOOL_BOUNDARY = 80.0

EXPECTED = ["ISSUE-204", "PR-411", "PR-518", "PR-233", "ISSUE-119", "PR-377", "ISSUE-451"]
DEPENDENCIES = {
    "PR-411": {"ISSUE-204"},
    "PR-518": {"ISSUE-204"},
    "PR-377": {"PR-233"},
    "ISSUE-451": {"PR-377"},
}
EVIDENCE_REQUIREMENTS = {
    "ISSUE-204": [
        ["critical"],
        ["platform-infra"],
        ["base image", "web-runtime.dockerfile"],
        ["pr-411"],
        ["pr-518"],
        ["blocking", "no active waiver", "no waiver"],
    ],
    "PR-411": [
        ["e2e-install-route"],
        ["web-platform"],
        ["issue-204"],
        ["customer-visible", "install route"],
        ["blocking", "no active waiver", "no waiver"],
    ],
    "PR-518": [
        ["gateway-canary"],
        ["edge-runtime"],
        ["issue-204"],
        ["public download", "region-aware"],
        ["blocking", "no active waiver", "no waiver"],
    ],
    "PR-233": [
        ["migration-replay"],
        ["billing"],
        ["pr-377"],
        ["pooled", "enterprise pooled", "settlement"],
        ["blocking", "no active waiver", "no waiver"],
    ],
    "ISSUE-119": [
        ["mobile"],
        ["app store", "ios/certificates/release.mobileprovision", "certificate"],
        ["upload"],
        ["blocking", "no active waiver", "no waiver"],
    ],
    "PR-377": [
        ["worker-integration"],
        ["jobs-runtime"],
        ["pr-233"],
        ["issue-451"],
        ["pooled", "settlement"],
        ["blocking", "no active waiver", "no waiver"],
    ],
    "ISSUE-451": [
        ["gates", "rel-884", "rollout gate"],
        ["owner-escalation-ready"],
        ["release-captains"],
        ["billing"],
        ["pr-377"],
        ["blocking", "no active waiver", "no waiver"],
    ],
}


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def norm_id(value: Any) -> str:
    text = str(value or "").strip().upper()
    match = re.search(r"(PR|ISSUE)-?\d+", text)
    if match:
        prefix, digits = match.group(1), re.search(r"\d+", match.group(0)).group(0)
        return f"{prefix}-{digits}"
    return text


def flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(flatten_text(v) for v in value)
    return str(value or "")


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
        "blocker_set": 0.0,
        "unblock_order": 0.0,
        "evidence": 0.0,
        "handoff_and_tool_use": 0.0,
    }

    if not REPORT.exists():
        finish({"score": 0.0, "breakdown": breakdown, "notes": ["missing /app/release_handoff.json"]})
        return
    try:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    except Exception as exc:
        finish({"score": 0.0, "breakdown": breakdown, "notes": [f"invalid release_handoff.json: {exc}"]})
        return

    blockers = report.get("blockers") if isinstance(report, dict) else None
    order = report.get("unblock_order") if isinstance(report, dict) else None
    if isinstance(blockers, list) and isinstance(order, list):
        breakdown["schema"] = SCHEMA_POINTS
    else:
        notes.append("handoff must contain blockers[] and unblock_order[]")
        blockers = blockers if isinstance(blockers, list) else []
        order = order if isinstance(order, list) else []

    submitted_ids = [norm_id(row.get("id")) for row in blockers if isinstance(row, dict)]
    submitted_set = set(submitted_ids)
    expected_set = set(EXPECTED)
    matched = submitted_set & expected_set
    extras = submitted_set - expected_set
    breakdown["blocker_set"] = max(
        0.0,
        BLOCKER_SET_POINTS * (len(matched) / len(expected_set)) - EXTRA_BLOCKER_PENALTY * len(extras),
    )
    missing = sorted(expected_set - submitted_set)
    if missing:
        notes.append(f"missing blockers: {', '.join(missing)}")
    if extras:
        notes.append(f"extra non-blockers: {', '.join(sorted(extras))}")

    order_ids = [norm_id(item) for item in order]
    positions = {item: idx for idx, item in enumerate(order_ids)}
    dep_checks = 0
    dep_ok = 0
    for item, deps in DEPENDENCIES.items():
        for dep in deps:
            dep_checks += 1
            if dep in positions and item in positions and positions[dep] < positions[item]:
                dep_ok += 1
            else:
                notes.append(f"dependency order wrong: {dep} must come before {item}")
    order_set_credit = ORDER_MEMBERSHIP_POINTS if set(order_ids) >= expected_set else 0.0
    breakdown["unblock_order"] = order_set_credit + (
        ORDER_DEPENDENCY_POINTS * dep_ok / dep_checks if dep_checks else ORDER_DEPENDENCY_POINTS
    )

    evidence_points = 0.0
    for row in blockers:
        if not isinstance(row, dict):
            continue
        item_id = norm_id(row.get("id"))
        if item_id not in expected_set:
            continue
        evidence_text = flatten_text(row.get("evidence")).lower()
        requirements = EVIDENCE_REQUIREMENTS[item_id]
        met = sum(1 for choices in requirements if any(choice in evidence_text for choice in choices))
        evidence_points += met / len(requirements)
        if met < len(requirements):
            notes.append(f"{item_id} evidence lacks exact owner-ready facts from release surfaces")
    breakdown["evidence"] = min(EVIDENCE_POINTS, evidence_points * (EVIDENCE_POINTS / len(expected_set)))

    events = load_events()
    used_tools = {event.get("tool") for event in events}
    submit_events = [event for event in events if event.get("tool") == "submit"]
    get_ids = {
        norm_id((event.get("arguments") or {}).get("id"))
        for event in events
        if event.get("tool") == "get" and isinstance(event.get("arguments"), dict)
    }
    check_ids = {
        norm_id((event.get("arguments") or {}).get("id"))
        for event in events
        if event.get("tool") == "checks" and isinstance(event.get("arguments"), dict)
    }
    review_ids = {
        norm_id((event.get("arguments") or {}).get("id"))
        for event in events
        if event.get("tool") == "reviews" and isinstance(event.get("arguments"), dict)
    }
    link_ids = {
        norm_id((event.get("arguments") or {}).get("id"))
        for event in events
        if event.get("tool") == "links" and isinstance(event.get("arguments"), dict)
    }
    decision_ids = {
        norm_id((event.get("arguments") or {}).get("id"))
        for event in events
        if event.get("tool") == "decisions" and isinstance(event.get("arguments"), dict)
    }
    handoff_score = 0.0
    handoff_note = report.get("handoff_note") if isinstance(report, dict) else ""
    if isinstance(handoff_note, str) and len(handoff_note.strip()) >= HANDOFF_NOTE_MIN_CHARS:
        handoff_score += HANDOFF_NOTE_POINTS
    else:
        notes.append("handoff_note is missing or too thin")
    if {"schema", "list", "get", "checks", "reviews", "links", "decisions", "gates", "submit"} <= used_tools:
        handoff_score += TOOL_SURFACE_POINTS
    else:
        notes.append("expected use of releasectl schema, list, get, checks, reviews, links, decisions, gates, and submit")
    if not events:
        notes.append("releasectl activity record missing; use releasectl")
    breakdown["handoff_and_tool_use"] = handoff_score

    score = sum(breakdown.values())
    if not submit_events:
        score = min(score, CAP_UNSUBMITTED)
        notes.append("expected a releasectl submit call")
    if "gates" not in used_tools:
        score = min(score, CAP_MISSING_REQUIRED_DISCOVERY)
        notes.append("missing release-gates lookup caps score")
    if "decisions" not in used_tools:
        score = min(score, CAP_MISSING_REQUIRED_DISCOVERY)
        notes.append("missing release-manager decision lookup caps score")
    uninspected = sorted(item for item in submitted_set & expected_set if item not in get_ids)
    if uninspected:
        score = min(score, CAP_MISSING_DETAIL_INSPECTION)
        notes.append(f"submitted blockers without detail inspection: {', '.join(uninspected)}")
    missing_checks = sorted(item for item in submitted_set & expected_set if item not in check_ids)
    if missing_checks:
        score = min(score, CAP_MISSING_EVIDENCE_SURFACE)
        notes.append(f"submitted blockers without check evidence lookup: {', '.join(missing_checks)}")
    missing_reviews = sorted(item for item in submitted_set & expected_set if item not in review_ids)
    if missing_reviews:
        score = min(score, CAP_MISSING_EVIDENCE_SURFACE)
        notes.append(f"submitted blockers without review evidence lookup: {', '.join(missing_reviews)}")
    missing_links = sorted(item for item in submitted_set & expected_set if item not in link_ids)
    if missing_links:
        score = min(score, CAP_MISSING_DEPENDENCY_SURFACE)
        notes.append(f"submitted blockers without dependency-link lookup: {', '.join(missing_links)}")
    missing_decisions = sorted(item for item in submitted_set & expected_set if item not in decision_ids)
    if missing_decisions:
        score = min(score, CAP_MISSING_EVIDENCE_SURFACE)
        notes.append(f"submitted blockers without release-manager decision lookup: {', '.join(missing_decisions)}")
    if missing:
        score = min(score, CAP_MISSING_TRUE_BLOCKER)
        notes.append("missing any true blocker caps score")
    if extras:
        score = min(score, CAP_EXTRA_NON_BLOCKERS)
        notes.append("extra non-blockers cap score")
    if dep_ok < dep_checks:
        score = min(score, CAP_DEPENDENCY_ORDER_ERROR)
        notes.append("dependency-order mistakes cap score")
    if not tool_boundary_ok():
        score = min(score, CAP_BROKEN_TOOL_BOUNDARY)
        notes.append("releasectl runtime boundary is readable or not installed setuid")
    finish({"score": round(clamp(score, 0.0, 100.0), 2), "breakdown": breakdown, "notes": notes})


if __name__ == "__main__":
    main()
