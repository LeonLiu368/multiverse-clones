from __future__ import annotations

import pytest

from aws_clone.seed.load_state import StateError, validate_state
from tests.helpers import fresh_state


def test_example_state_is_valid() -> None:
    validate_state(fresh_state())


def test_missing_required_top_level_key_fails() -> None:
    state = fresh_state()
    state.pop("s3")
    with pytest.raises(StateError, match="missing required state key: s3"):
        validate_state(state)


def test_duplicate_named_resource_fails() -> None:
    state = fresh_state()
    state["s3"]["buckets"].append({"name": "acme-payment-exports", "objects": []})
    with pytest.raises(StateError, match="duplicate s3.buckets name"):
        validate_state(state)
