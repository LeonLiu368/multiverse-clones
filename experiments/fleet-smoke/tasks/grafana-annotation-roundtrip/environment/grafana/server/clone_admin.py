from __future__ import annotations

from .state import GrafanaStore


def state_snapshot(store: GrafanaStore) -> dict[str, object]:
    return store.snapshot()


def mutations(store: GrafanaStore) -> list[dict[str, object]]:
    return store.mutation_log()
