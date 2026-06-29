from __future__ import annotations

from pathlib import Path

from sentry_clone.server.state import SentryStore, validate_state

from .helpers import fresh_state


def test_state_loading_and_validation() -> None:
    state = fresh_state()
    validate_state(state)
    store = SentryStore(state)
    assert store.org_slug() == "acme"
    assert store.issue("PAYMENTS-501")["id"] == "1001"


def test_runtime_state_persistence(tmp_path: Path) -> None:
    seed = tmp_path / "seed.json"
    runtime = tmp_path / "runtime.json"
    import json

    seed.write_text(json.dumps(fresh_state()), encoding="utf-8")
    store = SentryStore.from_runtime(seed, runtime)
    store.add_comment("PAYMENTS-501", "persist me")
    reloaded = SentryStore.from_runtime(seed, runtime)
    assert reloaded.comments("1001")[0]["text"] == "persist me"
    assert reloaded.mutation_log()[0]["action"] == "issue.comment"
