"""Sentry clone seed viewer. Conforms to the multiverse `sentry-clone` corpus state.json — top-level
`issues[]` + `events[]` (joined by `event.issue_id`), each event carrying `exception{type,value}` +
a separate `stacktrace{frames[]}` (frame `context_line`), plus projects/users/meta. Normalized to
the view's shape (issues[].events[].exception.stacktrace[frames]); the older nested `issues[].events[]`
shape is still accepted. Read-only; also loads the baked corpus from a `sentry-clone-service` image."""
from __future__ import annotations

import json
from typing import Any

from adapters.fileseed import FileSeedAdapter


def _tags_to_dict(tags: Any) -> dict:
    if isinstance(tags, dict):
        return tags
    out: dict = {}
    for t in tags or []:
        if isinstance(t, dict) and "key" in t:
            out[t["key"]] = t.get("value")
        elif isinstance(t, (list, tuple)) and len(t) == 2:
            out[str(t[0])] = t[1]
    return out


class SentryAdapter(FileSeedAdapter):
    id = "sentry"
    display_name = "Sentry"
    status = "active"
    ui_module = "sentry"
    sample_files = ("sentry.state.json",)
    # multiverse sentry-clone bakes the corpus into `sentry-clone-service:prod-v1` at
    # /srv/sentry-clone/corpus-state.json (Dockerfile.prod-v1, ENV SENTRY_CLONE_CORPUS_FILE).
    image_substrings = ("sentry-clone-service", "sentry-service", "sentry-clone")
    # prod-v1 bakes /srv/sentry-clone/corpus-state.json; the empty image mounts
    # /data/sentry-clone/state.json; the runtime mutable copy is /var/lib/sentry-clone/state.json.
    image_state_paths = ("/srv/sentry-clone/corpus-state.json", "/data/sentry-clone/state.json",
                         "/var/lib/sentry-clone/state.json", "/srv/sentry/state.json",
                         "/data/sentry/state.json")

    def _norm_event(self, e: dict) -> dict:
        exc = e.get("exception") or {}
        st = e.get("stacktrace") or exc.get("stacktrace") or {}
        frames = st.get("frames") if isinstance(st, dict) else st
        norm = [
            {"filename": f.get("filename"), "function": f.get("function"),
             "lineno": f.get("lineno"), "context": f.get("context_line") or f.get("context")}
            for f in (frames or [])
            if isinstance(f, dict)
        ]
        return {
            "id": e.get("id"),
            "timestamp": e.get("timestamp"),
            "message": e.get("message"),
            "tags": _tags_to_dict(e.get("tags")),
            "exception": {
                "type": exc.get("type"),
                "value": exc.get("value") or exc.get("message"),
                "stacktrace": norm,
            },
        }

    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        d = json.loads(raw)
        issues_raw = d.get("issues") or []
        # canonical corpus: events are top-level, linked by issue_id; old format: nested in the issue
        by_issue: dict[str, list] = {}
        for e in d.get("events") or []:
            by_issue.setdefault(e.get("issue_id"), []).append(e)

        issues = []
        for i in issues_raw:
            evs = i.get("events") or by_issue.get(i.get("id")) or []
            norm_evs = [self._norm_event(e) for e in evs]
            issues.append({
                "id": i.get("id"),
                "shortId": i.get("shortId") or i.get("short_id"),
                "title": i.get("title") or i.get("culprit") or (norm_evs[0]["message"] if norm_evs else ""),
                "culprit": i.get("culprit"),
                "level": i.get("level"),
                "status": i.get("status"),
                "count": i.get("count"),
                "userCount": i.get("userCount") or i.get("user_count"),
                "firstSeen": i.get("firstSeen") or i.get("first_seen"),
                "lastSeen": i.get("lastSeen") or i.get("last_seen"),
                "tags": _tags_to_dict(i.get("tags")),
                "events": norm_evs,
            })

        projects = d.get("projects") or []
        meta = d.get("meta") or {}
        org = meta.get("organization") or d.get("org") or d.get("organization") or ""
        if d.get("project"):
            project = d["project"]
        elif len(projects) > 1:
            project = f"{len(projects)} projects"
        elif projects:
            project = projects[0].get("name") or projects[0].get("slug") or ""
        else:
            project = ""

        return {
            "org": org,
            "project": project,
            "issues": issues,
            "stats": {
                "issues": len(issues),
                "events": sum(len(i["events"]) for i in issues),
                "unresolved": sum(1 for i in issues if i.get("status") == "unresolved"),
            },
        }
