"""The extension point that makes the dashboard scale across clones.

Routes and the frontend speak ONLY this normalized vocabulary, never Slack-specific shapes. A new
clone (gh-clone, linear, ticketvector) ships one CloneAdapter subclass + one frontend view dir; no
route or shell code changes. An adapter may back reads with a host-imported store (Slack) or the
clone's HTTP API (clones whose store isn't host-importable) — that choice is internal to the adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class BaseOption:
    """A selectable base corpus: a docker image with a baked DB, or a local export dir."""
    id: str
    kind: Literal["image", "dir"]
    ref: str  # image tag or directory path
    label: str
    detail: str = ""


@dataclass
class LoadResult:
    session_id: str
    base: str
    overlay: Optional[str]
    stats: dict[str, Any] = field(default_factory=dict)  # e.g. {"channels":N,"messages":N,"users":N}


# Normalized read shapes. `origin` is "base" or "overlay" so the UI can badge seeded rows.
Origin = Literal["base", "overlay"]


class CloneAdapter:
    """One service clone. Subclass and implement the methods below."""

    id: str = "clone"
    display_name: str = "Clone"
    status: Literal["active", "soon"] = "soon"
    ui_module: str = ""  # frontend view key, e.g. "slack"

    # ---- seed process -------------------------------------------------------
    def list_bases(self) -> list[BaseOption]:
        raise NotImplementedError

    def pull_base(self, ref: str) -> BaseOption:
        """docker-pull a registry tag, return it as a selectable base."""
        raise NotImplementedError

    def load(self, base_id: str, overlay_path: Optional[str] = None) -> LoadResult:
        """Build the merged workspace on the host (base + optional overlay), return a session."""
        raise NotImplementedError

    # ---- normalized reads (backed by the merged workspace) ------------------
    def meta(self) -> dict[str, Any]:
        """Workspace identity: {workspace, team_id, ...}."""
        raise NotImplementedError

    def containers(self) -> list[dict[str, Any]]:
        """Slack -> channels. Each: {id, name, ..., origin}."""
        raise NotImplementedError

    def entities(self) -> list[dict[str, Any]]:
        """Slack -> users. Each: {id, name, ..., origin}."""
        raise NotImplementedError

    def messages(self, container_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Top-level messages for a container, newest-first. Each carries `origin`."""
        raise NotImplementedError

    def thread(self, container_id: str, root_ts: str) -> list[dict[str, Any]]:
        """Thread parent + replies, oldest-first."""
        raise NotImplementedError

    def search(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    # ---- overlay editor (optional; adapters that support editing override these) ----
    def add_container(self, name: str, purpose: str = "") -> dict[str, Any]:
        raise NotImplementedError("this clone does not support editing")

    def add_message(self, container: str, author: str, text: str,
                    timestamp: Optional[str] = None) -> dict[str, Any]:
        raise NotImplementedError("this clone does not support editing")

    def remove_message(self, container_id: str, ts: str) -> dict[str, Any]:
        raise NotImplementedError("this clone does not support editing")

    def remove_container(self, container_id: str) -> dict[str, Any]:
        raise NotImplementedError("this clone does not support editing")

    def export_overlay(self) -> dict[str, Any]:
        raise NotImplementedError("this clone does not support exporting an overlay")

    def export_overlay_dir(self, dest_parent: str, name: str = "overlay") -> str:
        raise NotImplementedError("this clone does not support exporting an overlay directory")

    def export_patch(self) -> dict[str, Any]:
        """The mutations layer as the clone's patch op-list ({version, ops}) — applied onto the base
        at task standup (Slack import_export.py --patch / Jira apply_state_patch.py --patch)."""
        raise NotImplementedError("this clone does not support exporting a patch")

    # ---- whole-seed view (for read-only clones whose seed doesn't fit the chat/issue vocabulary
    #      — gauge logs/dashboards, sentry issues/events, github gh-seed script) ------------------
    def view(self) -> dict[str, Any]:
        """Return the full parsed seed payload for the frontend to render. Used by clones that load a
        single seed file and visualize it read-only, instead of the normalized container/message API."""
        raise NotImplementedError("this clone does not expose a seed view")

    def overlay_op(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Generic overlay edit op (used by clones whose edits don't fit the message/container
        verbs, e.g. Jira's add_issue/update_issue/add_comment/remove_*)."""
        raise NotImplementedError("this clone does not support editing")

    # ---- summary for the launcher tile --------------------------------------
    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "status": self.status,
            "ui_module": self.ui_module,
        }
