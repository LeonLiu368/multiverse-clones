"""Bridge to a service clone's own Python so the viewer reuses the exact code a task runs.

We deliberately do NOT vendor the clone's modules — we import them from the checkout on disk so
there is zero drift between what the viewer shows and what the agent sees. Point SLACK_CLONE_BASE at
the clone's `selfcontained/base` dir (the one holding slackgw/store.py + import_export.py)."""
from __future__ import annotations

import os
import sys
from functools import lru_cache

DEFAULT_SLACK_CLONE_BASE = (
    "/Users/leonliu/projects/abundant-slack-clone-mattermost/selfcontained/base"
)


def slack_clone_base() -> str:
    return os.environ.get("SLACK_CLONE_BASE", DEFAULT_SLACK_CLONE_BASE)


@lru_cache(maxsize=1)
def load_slack_clone():
    """Return (Store, import_export_module, slack_export_writer_or_None) from the clone checkout."""
    base = slack_clone_base()
    if not os.path.isdir(base):
        raise RuntimeError(
            f"SLACK_CLONE_BASE not found: {base!r}. Set SLACK_CLONE_BASE to the clone's "
            "selfcontained/base dir (containing slackgw/store.py + import_export.py)."
        )
    if base not in sys.path:
        sys.path.insert(0, base)
    from slackgw.store import Store  # type: ignore
    import import_export  # type: ignore

    try:
        import slack_export_writer  # type: ignore
    except Exception:
        slack_export_writer = None
    return Store, import_export, slack_export_writer
