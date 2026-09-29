"""A trivial fixture-backed adapter. Its only job is to prove the extension point: registering it
makes a second app appear and render through the SAME generic routes + shell, with zero changes to
app.py or the frontend shell. Delete or ignore in production."""
from __future__ import annotations

from typing import Any, Optional

from adapters.base import BaseOption, CloneAdapter, LoadResult

_USERS = [{"id": "U1", "name": "ada", "real_name": "Ada Lovelace"},
          {"id": "U2", "name": "alan", "real_name": "Alan Turing"}]
_CHANNELS = [{"id": "C1", "name": "general"}, {"id": "C2", "name": "random"}]
_MSGS = {
    "C1": [{"ts": "1.000000", "channel_id": "C1", "user": "U1", "text": "hello from the echo clone"}],
    "C2": [{"ts": "2.000000", "channel_id": "C2", "user": "U2", "text": "second container works too"}],
}


class EchoAdapter(CloneAdapter):
    id = "echo"
    display_name = "Echo (demo)"
    status = "active"
    ui_module = "generic"

    def list_bases(self) -> list[BaseOption]:
        return [BaseOption(id="fixture", kind="dir", ref="(fixture)", label="fixture corpus")]

    def load(self, base_id: str, overlay_path: Optional[str] = None) -> LoadResult:
        return LoadResult(session_id="echo", base=base_id, overlay=overlay_path,
                          stats={"channels": len(_CHANNELS), "users": len(_USERS)})

    def meta(self, session_id: Optional[str] = None) -> dict[str, Any]:
        return {"workspace": "echo", "team_id": "T_ECHO"}

    def containers(self, session_id: Optional[str] = None) -> list[dict[str, Any]]:
        return [{**c, "origin": "base"} for c in _CHANNELS]

    def entities(self, session_id: Optional[str] = None) -> list[dict[str, Any]]:
        return [{**u, "origin": "base"} for u in _USERS]

    def messages(self, container_id: str, limit: int = 100,
                 session_id: Optional[str] = None) -> list[dict[str, Any]]:
        return [{**m, "origin": "base", "reactions": []} for m in _MSGS.get(container_id, [])]

    def thread(self, container_id: str, root_ts: str,
               session_id: Optional[str] = None) -> list[dict[str, Any]]:
        return [m for m in self.messages(container_id) if m["ts"] == root_ts]

    def search(self, query: str, limit: int = 100,
               session_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = (query or "").lower()
        hits = []
        for ms in _MSGS.values():
            hits += [{**m, "origin": "base", "reactions": []} for m in ms if q in m["text"].lower()]
        return hits
