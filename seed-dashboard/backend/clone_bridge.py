"""Bridge to a service clone's own Python so the viewer reuses the exact code a task runs.

We deliberately do NOT vendor the clone's modules — we import them from the checkout on disk so
there is zero drift between what the viewer shows and what the agent sees. Point SLACK_CLONE_BASE at
the clone's `selfcontained/base` dir (the one holding slackgw/store.py + import_export.py)."""
from __future__ import annotations

import os
import sys
from functools import lru_cache

# Clone source lives in this repo's clones/ folder (see clones/MANIFEST.json). Every default below
# resolves relative to the repo, so the viewer works from any checkout; set the env vars to override.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIVERSE = os.path.expanduser(
    os.environ.get("MULTIVERSE_CLONES", os.path.join(REPO_ROOT, "clones"))
)


DEFAULT_SLACK_CLONE_BASE = os.path.join(MULTIVERSE, "abundant-slack-clone", "selfcontained", "base")


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
# ticketvector isn't part of this collection; by default we look for a checkout next to the repo.
DEFAULT_TICKETVECTOR_BASE = os.path.join(os.path.dirname(REPO_ROOT), "ticketvector")
DEFAULT_JIRA_DATA_BASE = os.path.join(MULTIVERSE, "abundant-jira-clone")


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
