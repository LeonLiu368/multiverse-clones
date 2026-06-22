"""Sentry clone seed viewer — a per-task state.json of issues + events (with stack traces). Read-only."""
from __future__ import annotations

import json
from typing import Any

from adapters.fileseed import FileSeedAdapter


class SentryAdapter(FileSeedAdapter):
    id = "sentry"
    display_name = "Sentry"
    status = "active"
    ui_module = "sentry"
    sample_files = ("sentry.state.json",)

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        d = json.loads(raw)
        issues = d.get("issues") or []
        return {
            "org": d.get("org") or d.get("organization") or "",
            "project": d.get("project") or "",
            "issues": issues,
            "stats": {
                "issues": len(issues),
                "events": sum(len(i.get("events") or []) for i in issues),
                "unresolved": sum(1 for i in issues if i.get("status") == "unresolved"),
            },
        }
