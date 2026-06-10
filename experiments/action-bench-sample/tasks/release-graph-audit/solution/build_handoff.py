#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SEVERITY_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def item_detail_paths(work_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(work_dir.glob("*.json")):
        if path.name in {"open-items.json", "gates.json"}:
            continue
        try:
            payload = load_json(path)
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("item"), dict):
            paths.append(path)
    return paths


def load_status(work_dir: Path, suffix: str, key: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted(work_dir.glob(f"*.{suffix}.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue
        value = payload.get(key)
        if isinstance(value, dict) and value.get("id"):
            rows[str(value["id"])] = value
    return rows


def has_failing_check(item: dict[str, Any]) -> bool:
    return any(
        check.get("conclusion") != "success"
        and bool(check.get("required", True))
        and bool(check.get("blocking", True))
        and not bool(check.get("waived", False))
        for check in item.get("checks", [])
    )


def is_release_blocker(item: dict[str, Any]) -> bool:
    return "release-blocker" in item.get("labels", [])


def is_train_watch(item: dict[str, Any]) -> bool:
    return "train-watch" in item.get("labels", [])


def is_waived_or_nonblocking(item: dict[str, Any]) -> bool:
    decision = item.get("decision") or {}
    if isinstance(decision, dict) and decision.get("release_decision") in {"waived", "not_blocking", "monitor"}:
        return True
    notes = str(item.get("notes", "")).lower()
    return any(token in notes for token in ["waiver", "not blocking", "not a blocker"])


def is_actionable_detail(item: dict[str, Any]) -> bool:
    notes = str(item.get("notes", "")).lower()
    return (
        has_failing_check(item)
        or bool(item.get("blocking_reviewers"))
        or bool(item.get("blocks"))
        or item.get("severity") in {"critical", "high"}
        or "blocks" in notes
    )


def candidate_ids(open_items_path: Path) -> list[str]:
    items = load_json(open_items_path)["items"]
    candidates = set()
    deferred_terms = {
        "analytics",
        "beta",
        "counter",
        "counters",
        "dashboard",
        "digest note",
        "fixture",
        "load-test",
        "post-train",
        "reminder",
        "screenshot",
    }
    for item in items:
        labels = set(item.get("labels", []))
        repo = str(item.get("repo", ""))
        title = str(item.get("title", "")).lower()
        if not (is_release_blocker(item) or is_train_watch(item)):
            continue
        if any(term in title for term in deferred_terms):
            continue
        if labels & {"infra", "customer-visible", "billing", "mobile"}:
            candidates.add(item["id"])
        elif repo == "api-gateway" and is_release_blocker(item):
            candidates.add(item["id"])
        elif item.get("severity") == "critical":
            candidates.add(item["id"])
    return [item["id"] for item in items if item["id"] in candidates]


def gate_ids(gates_path: Path) -> list[str]:
    gates = load_json(gates_path).get("gates", [])
    return [gate["id"] for gate in gates if isinstance(gate, dict) and gate.get("id")]


def followup_ids(work_dir: Path) -> list[str]:
    detail_paths = item_detail_paths(work_dir)
    loaded = {path.stem for path in detail_paths}
    links = load_status(work_dir, "links", "links")
    followups: list[str] = []
    seen = set(loaded)
    for item in links.values():
        for item_id in item.get("blocks", []) + item.get("depends_on", []):
            if item_id not in seen:
                seen.add(item_id)
                followups.append(item_id)
    return followups


def preliminary_ids(work_dir: Path) -> list[str]:
    ids: list[str] = []
    for path in item_detail_paths(work_dir):
        item = load_json(path)["item"]
        notes = str(item.get("notes", "")).lower()
        candidate = (
            item.get("state") == "open"
            and (is_release_blocker(item) or is_train_watch(item) or "rollout-gate" in item.get("labels", []))
            and not is_waived_or_nonblocking(item)
            and (
                item.get("severity") in {"critical", "high"}
                or "customer-visible" in item.get("labels", [])
                or "billing" in item.get("labels", [])
                or "blocks" in notes
            )
        )
        if candidate:
            ids.append(item["id"])
    return ids


def merge_evidence(work_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    checks = load_status(work_dir, "checks", "status").get(item["id"], {})
    reviews = load_status(work_dir, "reviews", "status").get(item["id"], {})
    links = load_status(work_dir, "links", "links").get(item["id"], {})
    decision = load_status(work_dir, "decisions", "decision").get(item["id"], {})
    merged = dict(item)
    merged["checks"] = checks.get("checks", [])
    merged["blocking_reviewers"] = reviews.get("blocking_reviewers", [])
    merged["depends_on"] = links.get("depends_on", [])
    merged["blocks"] = links.get("blocks", [])
    merged["decision"] = decision
    return merged


def select_blockers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["id"]: item for item in items}
    selected = {
        item["id"]
        for item in items
        if is_release_blocker(item)
        and item.get("state") == "open"
        and not is_waived_or_nonblocking(item)
        and is_actionable_detail(item)
    }

    changed = True
    while changed:
        changed = False
        for item in items:
            if item["id"] in selected or item.get("state") != "open":
                continue
            deps = set(item.get("depends_on", []))
            dependency_linked = bool(deps & selected)
            actionable = has_failing_check(item) or bool(item.get("blocking_reviewers"))
            if dependency_linked and actionable and not is_waived_or_nonblocking(item):
                selected.add(item["id"])
                changed = True

    return [item for item_id, item in by_id.items() if item_id in selected]


def evidence_for(item: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    labels = item.get("labels", [])
    owners = item.get("owners", [])
    paths = item.get("paths", [])
    if owners:
        evidence.append(f"responsible owners: {', '.join(owners)}")
    if labels:
        evidence.append(f"release labels: {', '.join(labels)}")
    if paths:
        evidence.append(f"affected release paths: {', '.join(paths)}")
    if "rollout-gate" in labels:
        evidence.append("REL-884 rollout gate tracked outside the shallow triage list")

    if "release-blocker" in labels:
        evidence.append(f"{item['severity']} release-blocker item")
    elif "train-watch" in labels:
        evidence.append(f"{item['severity']} train-watch item linked to unresolved release work")

    failing = [check["name"] for check in item.get("checks", []) if check.get("conclusion") != "success"]
    if failing:
        evidence.append(f"failing checks: {', '.join(failing)}")

    reviewers = item.get("blocking_reviewers", [])
    if reviewers:
        evidence.append(f"missing required owner approval from {', '.join(reviewers)}")

    depends_on = item.get("depends_on", [])
    if depends_on:
        evidence.append(f"depends on unresolved train work: {', '.join(depends_on)}")

    blocks = item.get("blocks", [])
    if blocks:
        evidence.append(f"blocks dependency-linked work: {', '.join(blocks)}")

    notes = item.get("notes")
    if notes:
        evidence.append(notes)
    decision = item.get("decision") or {}
    if isinstance(decision, dict) and decision.get("release_decision"):
        evidence.append(f"release decision: {decision.get('release_decision')} ({decision.get('reason', 'no note')})")
    return evidence


def ordered_blockers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["id"]: item for item in items}
    remaining = set(by_id)
    ordered: list[dict[str, Any]] = []

    while remaining:
        ready = [
            item_id
            for item_id in remaining
            if all(dep not in by_id or dep not in remaining for dep in by_id[item_id].get("depends_on", []))
        ]
        ready.sort(
            key=lambda item_id: (
                SEVERITY_PRIORITY.get(by_id[item_id].get("severity"), 9),
                by_id[item_id]["kind"] != "issue",
                by_id[item_id]["repo"],
                by_id[item_id]["number"],
            )
        )
        chosen = ready[0]
        remaining.remove(chosen)
        ordered.append(by_id[chosen])
    return ordered


def build_handoff(work_dir: Path, destination: Path) -> None:
    detail_paths = item_detail_paths(work_dir)
    items = select_blockers([merge_evidence(work_dir, load_json(path)["item"]) for path in detail_paths])
    ordered = ordered_blockers(items)

    blockers = []
    for rank, item in enumerate(ordered, start=1):
        blockers.append(
            {
                "id": item["id"],
                "repo": item["repo"],
                "number": item["number"],
                "kind": item["kind"],
                "title": item["title"],
                "owners": item["owners"],
                "evidence": evidence_for(item),
                "recommended_rank": rank,
            }
        )

    independent = [item for item in ordered if not item.get("depends_on")]
    handoff_note = (
        "I started from the release-room notes and the broad open-item graph, then pulled detail records "
        "only for release blockers and dependency-linked train work with failed checks or missing owner review. "
        f"The independent same-day escalations are {', '.join(item['id'] for item in independent)}. "
        "Dependency-linked work should follow the submitted unblock_order so upstream issues are handled before "
        "the PRs they block. Each blocker entry includes the responsible owners plus evidence from checks, "
        "required reviews, dependency links, and release notes so the release captain can forward the escalation."
    )

    destination.write_text(
        json.dumps(
            {
                "blockers": blockers,
                "unblock_order": [item["id"] for item in ordered],
                "handoff_note": handoff_note,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: build_handoff.py candidates <open-items.json> | gates <gates.json> | preliminary <work-dir> | followups <work-dir> | handoff <work-dir> <output.json>")
    mode = sys.argv[1]
    if mode == "candidates" and len(sys.argv) == 3:
        for item_id in candidate_ids(Path(sys.argv[2])):
            print(item_id)
        return
    if mode == "gates" and len(sys.argv) == 3:
        for item_id in gate_ids(Path(sys.argv[2])):
            print(item_id)
        return
    if mode == "preliminary" and len(sys.argv) == 3:
        for item_id in preliminary_ids(Path(sys.argv[2])):
            print(item_id)
        return
    if mode == "followups" and len(sys.argv) == 3:
        for item_id in followup_ids(Path(sys.argv[2])):
            print(item_id)
        return
    if mode == "handoff" and len(sys.argv) == 4:
        build_handoff(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    raise SystemExit("invalid arguments")


if __name__ == "__main__":
    main()
