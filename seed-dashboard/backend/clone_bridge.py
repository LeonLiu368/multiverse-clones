"""Bridge to a service clone's own Python so the viewer reuses the exact code a task runs.

We deliberately do NOT vendor the clone's modules — we import them from the checkout on disk so
there is zero drift between what the viewer shows and what the agent sees. Point SLACK_CLONE_BASE at
the clone's `selfcontained/base` dir (the one holding slackgw/store.py + import_export.py)."""
from __future__ import annotations

import os
import sys
from functools import lru_cache

# Canonical clone source now lives in ~/projects/multiverse-clones/clones (see the repo's
# MANIFEST.json). We prefer it and fall back to the older standalone abundant-* checkouts so the
# viewer keeps working on a box that only has one of them.
MULTIVERSE = os.path.expanduser(
    os.environ.get("MULTIVERSE_CLONES", "/Users/leonliu/projects/multiverse-clones/clones")
)


def _first_existing(*paths: str) -> str:
    for p in paths:
        if p and os.path.isdir(p):
            return p
    return paths[0]  # a stable default even if missing (callers raise a clear error)


DEFAULT_SLACK_CLONE_BASE = _first_existing(
    os.path.join(MULTIVERSE, "abundant-slack-clone", "selfcontained", "base"),
    "/Users/leonliu/projects/abundant-slack-clone-mattermost/selfcontained/base",
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


# ---- Jira clone (abundant-jira-clone data + images) on the ticketvector runtime ----------------
# The Jira clone's data is a single state.json (ticketvector format). The runtime/store that reads &
# writes it is ticketvector's FakePlaneBackend — we import it by path (zero vendoring), exactly like
# the Slack store bridge. JIRA_DATA_BASE points at the abundant-jira-clone checkout (state.json
# fixtures + the jira-gateway images); TICKETVECTOR_BASE points at the ticketvector checkout.
# state.json + apply_state_patch.py + jira-gateway images now live in the multiverse jira clone;
# the read/write engine (ticketvector's FakePlaneBackend) is not vendored there, so it stays on the
# standalone ticketvector checkout (the state.json format is identical, so this is drift-free).
DEFAULT_TICKETVECTOR_BASE = "/Users/leonliu/projects/ticketvector"
DEFAULT_JIRA_DATA_BASE = _first_existing(
    os.path.join(MULTIVERSE, "abundant-jira-clone"),
    "/Users/leonliu/projects/abundant-jira-clone",
)


def ticketvector_base() -> str:
    return os.environ.get("TICKETVECTOR_BASE", DEFAULT_TICKETVECTOR_BASE)


def jira_data_base() -> str:
    return os.environ.get("JIRA_DATA_BASE", DEFAULT_JIRA_DATA_BASE)


@lru_cache(maxsize=1)
def load_jira_clone():
    """Return ticketvector's FakePlaneBackend class (reads/writes a state.json) and helpers module."""
    base = ticketvector_base()
    if not os.path.isdir(base):
        raise RuntimeError(
            f"TICKETVECTOR_BASE not found: {base!r}. Set TICKETVECTOR_BASE to the ticketvector "
            "checkout (containing world_issues/client.py)."
        )
    if base not in sys.path:
        sys.path.insert(0, base)
    from world_issues import client as wi_client  # type: ignore
    return wi_client.FakePlaneBackend, wi_client
