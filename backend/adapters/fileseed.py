"""Base for read-only single-file seed adapters (gauge, sentry, github).

These clones don't fit the chat/issue normalized vocabulary, and (per clone-task-builder) their seed
is a single per-task file with no shared prod corpus to merge against. So the adapter just loads the
file and exposes the parsed payload through `view()`; the frontend renders it. Bases = bundled
samples under `seed-dashboard/samples/`; any other file loads via a `file:<path>` base id."""
from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from adapters.base import BaseOption, CloneAdapter, LoadResult

SAMPLES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "samples"))


class FileSeedAdapter(CloneAdapter):
    sample_files: tuple[str, ...] = ()  # filenames under samples/ for this clone

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._current: Optional[str] = None

    def list_bases(self) -> list[BaseOption]:
        out: list[BaseOption] = []
        for fn in self.sample_files:
            p = os.path.join(SAMPLES_DIR, fn)
            if os.path.isfile(p):
                out.append(BaseOption(id=f"file:{os.path.abspath(p)}", kind="file", ref=p,
                                      label=f"samples/{fn}", detail="bundled sample seed"))
        return out

    def load(self, base_id: str, overlay_path: Optional[str] = None) -> LoadResult:
        path = base_id[5:] if base_id.startswith("file:") else base_id
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(path):
            raise RuntimeError(f"seed file not found: {path}")
        raw = open(path, encoding="utf-8", errors="replace").read()
        parsed = self._parse(raw, path)
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {"path": path, "raw": raw, "parsed": parsed}
        self._current = session_id
        return LoadResult(session_id=session_id, base=base_id, overlay=None,
                          stats=parsed.get("stats", {}))

    def _sess(self, session_id: Optional[str] = None) -> dict[str, Any]:
        sid = session_id or self._current
        if not sid or sid not in self._sessions:
            raise RuntimeError("no loaded session — call load() first")
        return self._sessions[sid]

    def meta(self, session_id: Optional[str] = None) -> dict[str, Any]:
        s = self._sess(session_id)
        return {"path": s["path"], "stats": s["parsed"].get("stats", {})}

    def view(self, session_id: Optional[str] = None) -> dict[str, Any]:
        return self._sess(session_id)["parsed"]

    # subclasses implement: parse raw seed text -> a JSON-able payload (include a "stats" dict)
    def _parse(self, raw: str, path: str) -> dict[str, Any]:
        raise NotImplementedError
