from __future__ import annotations

from typing import Any

from .state import SentryStore


def state_snapshot(store: SentryStore) -> dict[str, Any]:
    return store.snapshot()


def mutations(store: SentryStore) -> list[dict[str, Any]]:
    return store.mutation_log()
