"""Resolve named workspaces from a baked-in catalog directory.

A *catalog* is just a directory of canonical seed JSON files (``<name>.json``).
In the shipped image this is ``/srv/workspaces`` (overridable via the
``SLACK_WORKSPACE_DIR`` env var). The catalog lets a task select its workspace
by NAME (e.g. ``SLACK_WORKSPACE=acme-incident``) without the seed data ever
living inside the task directory.
"""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_ROOT = "/srv/workspaces"


def catalog_root(root: str | None = None) -> str:
    """The catalog directory: explicit arg > ``$SLACK_WORKSPACE_DIR`` > default."""
    return root or os.environ.get("SLACK_WORKSPACE_DIR") or DEFAULT_ROOT


def workspace_path(name: str, root: str | None = None) -> str | None:
    """Path to ``<root>/<name>.json`` if it exists, else ``None``."""
    if not name:
        return None
    path = os.path.join(catalog_root(root), f"{name}.json")
    return path if os.path.isfile(path) else None


def list_workspaces(root: str | None = None) -> list[str]:
    """Sorted names (basename without ``.json``) available in the catalog."""
    d = catalog_root(root)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


def read_workspace(name: str, root: str | None = None) -> dict[str, Any]:
    """Parse and return the canonical seed dict for ``name``.

    Raises ``KeyError(name)`` if the workspace is not in the catalog.
    """
    path = workspace_path(name, root)
    if not path:
        raise KeyError(name)
    with open(path) as f:
        return json.load(f)


def load_named(name: str, db_path: str, root: str | None = None) -> dict[str, int]:
    """Load catalog workspace ``name`` into the SQLite db at ``db_path``."""
    from .load import load_seed

    return load_seed(read_workspace(name, root), db_path)
