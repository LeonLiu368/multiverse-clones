from __future__ import annotations

import pytest

import json

from gauge.server.state import GaugeStore, StateError, validate_state

from .helpers import fresh_state


def test_state_loading_and_validation() -> None:
    state = fresh_state()
    validate_state(state)
    store = GaugeStore(state)
    assert store.current_user()["login"] == "agent"
    assert store.org()["name"] == "acme"


def test_state_rejects_missing_required_key() -> None:
    state = fresh_state()
    del state["dashboards"]
    with pytest.raises(StateError):
        validate_state(state)


def test_annotation_persists_to_runtime_state(tmp_path) -> None:
    seed = tmp_path / "seed.json"
    runtime = tmp_path / "runtime.json"
    seed.write_text(json.dumps(fresh_state()), encoding="utf-8")
    store = GaugeStore.from_runtime(seed, runtime)
    store.add_annotation({"dashboardUID": "dash-payment-webhooks", "panelId": 1, "text": "persisted", "tags": ["persist"]})

    reloaded = GaugeStore.from_runtime(seed, runtime)
    assert reloaded.annotations()[0]["text"] == "persisted"
    assert reloaded.mutation_log()[0]["action"] == "annotation.create"
