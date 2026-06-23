"""Base for read-only single-file seed adapters (gauge, sentry, github, figma).

These clones don't fit the chat/issue normalized vocabulary, and (per clone-task-builder) their seed
is a single per-task file. So the adapter loads the file and exposes the parsed payload through
`view()`; the frontend renders it. A seed can come from:
  • a bundled sample under `seed-dashboard/samples/`,
  • an uploaded file (`POST /api/{app}/load_file` → `file:<temp>`), or
  • a clone **gateway image** that bakes the state at a known path (set `image_substrings` +
    `image_state_paths`); we extract that file and parse it the same way."""
from __future__ import annotations

import os
import tempfile
import uuid
from typing import Any, Optional

import dockerutil
from adapters.base import BaseOption, CloneAdapter, LoadResult

SAMPLES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "samples"))


class FileSeedAdapter(CloneAdapter):
    sample_files: tuple[str, ...] = ()       # filenames under samples/ for this clone
    image_substrings: tuple[str, ...] = ()   # docker repos to offer as image bases (e.g. gauge-gateway)
    image_state_paths: tuple[str, ...] = ()  # candidate baked-state file paths inside such images

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._current: Optional[str] = None

    def list_bases(self) -> list[BaseOption]:
        out: list[BaseOption] = []
        if self.image_substrings:
            for ref in dockerutil.list_images(*self.image_substrings):
                out.append(BaseOption(id=ref, kind="image", ref=ref, label=ref,
                                      detail="baked state (docker image)"))
        for fn in self.sample_files:
            p = os.path.join(SAMPLES_DIR, fn)
            if os.path.isfile(p):
                out.append(BaseOption(id=f"file:{os.path.abspath(p)}", kind="file", ref=p,
                                      label=f"samples/{fn}", detail="bundled sample seed"))
        return out

    def pull_base(self, ref: str) -> BaseOption:
        dockerutil.pull_image(ref)
        return BaseOption(id=ref, kind="image", ref=ref, label=ref, detail="pulled from registry")

    def load(self, base_id: str, overlay_path: Optional[str] = None) -> LoadResult:
        if base_id.startswith("file:") or os.path.isfile(base_id):
            path = base_id[5:] if base_id.startswith("file:") else base_id
            path = os.path.abspath(os.path.expanduser(path))
            if not os.path.isfile(path):
                raise RuntimeError(f"seed file not found: {path}")
            src, raw = path, open(path, encoding="utf-8", errors="replace").read()
        else:  # docker image — extract the baked state file
            if not self.image_state_paths:
                raise RuntimeError(f"{self.id} does not support image bases")
            workdir = tempfile.mkdtemp(prefix=f"seedview-{self.id}-")
            dest = os.path.join(workdir, "state")
            last = ""
            for p in self.image_state_paths:
                try:
                    dockerutil.extract_file(base_id, p, dest)
                    break
                except Exception as e:
                    last = str(e)
            else:
                raise RuntimeError(
                    f"no baked state in {base_id} (probed {self.image_state_paths}). {last}"
                )
            src, raw = base_id, open(dest, encoding="utf-8", errors="replace").read()

        parsed = self._parse(raw, src)
        if overlay_path:  # optional overlay file, merged by the clone-specific _merge
            ov_path = os.path.abspath(os.path.expanduser(overlay_path))
            parsed = self._merge(parsed, self._parse(open(ov_path, encoding="utf-8", errors="replace").read(), ov_path))
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {"path": src, "raw": raw, "parsed": parsed}
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

    # clones that support an overlay file override this to merge it onto the parsed base
    def _merge(self, base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(f"{self.id} does not support an overlay")
