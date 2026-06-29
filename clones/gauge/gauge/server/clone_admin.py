from __future__ import annotations

from .state import GaugeStore


def state_snapshot(store: GaugeStore) -> dict[str, object]:
    return store.snapshot()


def mutations(store: GaugeStore) -> list[dict[str, object]]:
    return store.mutation_log()
