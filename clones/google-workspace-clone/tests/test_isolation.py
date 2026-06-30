"""Isolation / import-leak (R6.3, R2.k). In the THIN agent image these must hold:
the seed db is absent, the gateway's seed generator is NOT importable (so the answer
cannot be recomputed), and no `api/`/`seed/` source survives. Run inside the agent
container (e.g. via tests/test.sh) — the asserts that need the agent layout are
skipped when the gateway source is present (i.e. when run from the dev checkout).
"""
import importlib.util
import os
import shutil

import gwsclone


def _agent_image() -> bool:
    """True when running in the stripped agent image (no seed package present)."""
    return importlib.util.find_spec("gwsclone.seed") is None


def test_no_seed_db_on_disk():
    """R6.3: the agent must not carry the seeded SQLite db (the answer key)."""
    state = os.environ.get("CLONE_STATE_PATH", "/srv/gws.db")
    assert not os.path.exists(state), f"LEAK: {state} present — agent could read the answer key"


def test_seed_generator_not_importable():
    """R2.k/R6.3: a deterministic generator left in the agent lets it RECOMPUTE the
    answer even when grep finds nothing. In the agent image `gwsclone.seed` is gone."""
    if not _agent_image():
        # dev checkout ships the full package; this gate is enforced in the agent image
        import pytest
        pytest.skip("gateway source present (dev checkout); enforced in the thin agent image")
    import pytest
    with pytest.raises(ModuleNotFoundError):
        __import__("gwsclone.seed")


def test_api_and_seed_source_absent_in_agent():
    """R2.k check #3: no api/ or seed/ source dirs in the agent package tree."""
    if not _agent_image():
        import pytest
        pytest.skip("gateway source present (dev checkout); enforced in the thin agent image")
    pkg_dir = os.path.dirname(gwsclone.__file__)
    assert not os.path.exists(os.path.join(pkg_dir, "api"))
    assert not os.path.exists(os.path.join(pkg_dir, "seed"))


def test_world_building_tools_absent_from_agent():
    """R6.3/R2.g: import/seed/hydrate must not be callable from the agent PATH."""
    for op in ("seed", "import-state", "hydrate", "snapshot"):
        assert shutil.which(op) is None, f"world-building tool '{op}' on agent PATH"
