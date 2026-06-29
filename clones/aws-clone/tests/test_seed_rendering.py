from __future__ import annotations

import json

from aws_clone.seed.load_state import ensure_runtime_state, load_state
from aws_clone.seed.render_ready_init import render_ready_init
from tests.helpers import example_state_path


def test_render_ready_init_uses_seed_entrypoints() -> None:
    rendered = render_ready_init()
    assert "aws_clone.seed.wait_ready" in rendered
    assert "aws_clone.seed.load_state" in rendered


def test_runtime_state_is_copied_atomically(tmp_path) -> None:
    runtime = tmp_path / "state.json"
    state = ensure_runtime_state(example_state_path(), runtime)
    assert runtime.exists()
    assert load_state(runtime) == state
    original = json.loads(runtime.read_text(encoding="utf-8"))
    assert original["s3"]["buckets"][0]["name"] == "acme-payment-exports"
