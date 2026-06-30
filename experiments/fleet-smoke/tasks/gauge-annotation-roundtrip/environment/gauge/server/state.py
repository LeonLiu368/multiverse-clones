from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_STATE_FILE = "/data/gauge/state.json"
DEFAULT_RUNTIME_STATE_FILE = "/var/lib/gauge/state.json"


class StateError(ValueError):
    pass


REQUIRED_TOP_LEVEL = {
    "meta": dict,
    "users": list,
    "datasources": list,
    "dashboards": list,
    "alerts": list,
    "metrics": dict,
    "logs": dict,
    "annotations": list,
    "mutation_log": list,
}

OPTIONAL_TOP_LEVEL = {
    "alert_instances": list,
    "alert_state_history": list,
}


def state_file_from_env() -> Path:
    return Path(os.environ.get("GAUGE_STATE_FILE", DEFAULT_STATE_FILE))


def runtime_state_file_from_env() -> Path:
    return Path(os.environ.get("GAUGE_RUNTIME_STATE_FILE", DEFAULT_RUNTIME_STATE_FILE))


def _validate_uid_collection(name: str, items: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise StateError(f"{name}[{index}] must be an object")
        uid = item.get("uid")
        if not isinstance(uid, str) or not uid:
            raise StateError(f"{name}[{index}].uid is required")
        if uid in seen:
            raise StateError(f"duplicate {name} uid: {uid}")
        seen.add(uid)


def validate_state(state: dict[str, Any]) -> None:
    if not isinstance(state, dict):
        raise StateError("state root must be an object")

    for key, expected_type in REQUIRED_TOP_LEVEL.items():
        if key not in state:
            raise StateError(f"missing required state key: {key}")
        if not isinstance(state[key], expected_type):
            raise StateError(f"state.{key} must be {expected_type.__name__}")
    for key, expected_type in OPTIONAL_TOP_LEVEL.items():
        state.setdefault(key, [])
        if not isinstance(state[key], expected_type):
            raise StateError(f"state.{key} must be {expected_type.__name__}")

    _validate_uid_collection("datasources", state["datasources"])
    _validate_uid_collection("dashboards", state["dashboards"])
    _validate_uid_collection("alerts", state["alerts"])

    datasource_uids = {item["uid"] for item in state["datasources"]}
    dashboard_uids = {item["uid"] for item in state["dashboards"]}
    for dashboard in state["dashboards"]:
        panels = dashboard.get("panels", [])
        if not isinstance(panels, list):
            raise StateError(f"dashboard {dashboard['uid']} panels must be a list")
        for panel in panels:
            ds_uid = panel.get("datasource_uid")
            if ds_uid and ds_uid not in datasource_uids:
                raise StateError(f"panel datasource not found: {ds_uid}")
    for alert in state["alerts"]:
        dash_uid = alert.get("dashboard_uid")
        if dash_uid and dash_uid not in dashboard_uids:
            raise StateError(f"alert dashboard not found: {dash_uid}")


def load_state(path: str | Path | None = None) -> dict[str, Any]:
    state_path = Path(path) if path else state_file_from_env()
    with state_path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    validate_state(state)
    return state


@dataclass
class GaugeStore:
    state: dict[str, Any]
    runtime_state_path: Path | None = None

    def __post_init__(self) -> None:
        validate_state(self.state)
        self._lock = threading.RLock()
        self._next_annotation_id = self._compute_next_annotation_id()

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "GaugeStore":
        return cls(load_state(path))

    @classmethod
    def from_runtime(
        cls,
        seed_path: str | Path | None = None,
        runtime_path: str | Path | None = None,
    ) -> "GaugeStore":
        seed = Path(seed_path) if seed_path else state_file_from_env()
        runtime = Path(runtime_path) if runtime_path else runtime_state_file_from_env()
        if runtime.exists():
            state = load_state(runtime)
        else:
            state = load_state(seed)
            _write_state_atomic(runtime, state)
        return cls(state, runtime_state_path=runtime)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self.state)

    def meta_now(self) -> str:
        now = self.state.get("meta", {}).get("now")
        return str(now or "1970-01-01T00:00:00Z")

    def current_user(self) -> dict[str, Any]:
        users = self.state.get("users") or []
        if users:
            user = copy.deepcopy(users[0])
        else:
            user = {"id": 1, "login": "agent", "name": "Agent User", "role": "Editor"}
        user.setdefault("email", f"{user.get('login', 'agent')}@example.local")
        user.setdefault("orgId", 1)
        return user

    def org(self) -> dict[str, Any]:
        workspace = self.state.get("meta", {}).get("workspace") or "main"
        return {"id": 1, "name": str(workspace), "address": {}}

    def datasources(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.state["datasources"])

    def datasource(self, uid: str) -> dict[str, Any] | None:
        for item in self.state["datasources"]:
            if item.get("uid") == uid:
                return copy.deepcopy(item)
        return None

    def dashboards(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.state["dashboards"])

    def dashboard(self, uid: str) -> dict[str, Any] | None:
        for item in self.state["dashboards"]:
            if item.get("uid") == uid:
                return copy.deepcopy(item)
        return None

    def alerts(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.state["alerts"])

    def alert(self, uid: str) -> dict[str, Any] | None:
        for item in self.state["alerts"]:
            if item.get("uid") == uid:
                return copy.deepcopy(item)
        return None

    def alert_instances(self, state_filter: str | None = None) -> list[dict[str, Any]]:
        instances = copy.deepcopy(self.state.get("alert_instances", []))
        if state_filter:
            instances = [item for item in instances if item.get("state") == state_filter]
        return instances

    def alert_state_history(self, rule_uid: str) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in self.state.get("alert_state_history", [])
            if item.get("rule_uid") == rule_uid or item.get("alert_uid") == rule_uid
        ]

    def annotations(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self.state["annotations"])

    def mutation_log(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self.state["mutation_log"])

    def add_annotation(self, annotation: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            created = copy.deepcopy(annotation)
            created.setdefault("id", self._next_annotation_id)
            self._next_annotation_id = max(self._next_annotation_id, int(created["id"]) + 1)
            created.setdefault("time", self.meta_now())
            created.setdefault("createdBy", "agent")
            created.setdefault("tags", [])
            self.state["annotations"].append(created)
            self._record_mutation("annotation.create", created)
            self._persist_locked()
            return copy.deepcopy(created)

    def _record_mutation(self, action: str, after: dict[str, Any]) -> None:
        self.state["mutation_log"].append(
            {
                "id": len(self.state["mutation_log"]) + 1,
                "ts": self.meta_now(),
                "actor": "agent",
                "action": action,
                "target": after.get("id") or after.get("uid") or after.get("dashboardUID"),
                "after": copy.deepcopy(after),
            }
        )

    def _compute_next_annotation_id(self) -> int:
        ids = []
        for annotation in self.state.get("annotations", []):
            value = annotation.get("id")
            if isinstance(value, int):
                ids.append(value)
        return max(ids, default=0) + 1

    def _persist_locked(self) -> None:
        if self.runtime_state_path is not None:
            _write_state_atomic(self.runtime_state_path, self.state)


def _write_state_atomic(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
