from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .errors import ConfigError, redact


DEFAULT_CONFIG_PATH = Path.home() / ".world-issues.json"


@dataclass(frozen=True)
class Config:
    base_url: str | None = None
    api_key: str | None = None
    workspace: str | None = None
    default_project: str | None = None
    actor: str = "agent"
    output: str = "plain"
    backend: str = "fake"
    state_file: Path = Path(".ticketvector/state.json")
    config_path: Path = DEFAULT_CONFIG_PATH

    def redacted_dict(self) -> dict[str, Any]:
        return redact(
            {
                "base_url": self.base_url,
                "api_key": self.api_key,
                "workspace": self.workspace,
                "default_project": self.default_project,
                "actor": self.actor,
                "output": self.output,
                "backend": self.backend,
                "state_file": str(self.state_file),
                "config_path": str(self.config_path),
            }
        )

    def require_plane(self) -> None:
        missing = []
        if not self.base_url:
            missing.append("PLANE_BASE_URL or config base_url")
        if not self.api_key:
            missing.append("PLANE_API_KEY or config api_key")
        if not self.workspace:
            missing.append("WORLD_ISSUES_WORKSPACE or config workspace")
        if not self.default_project:
            missing.append("WORLD_ISSUES_DEFAULT_PROJECT or config default_project")
        if missing:
            raise ConfigError("missing Plane configuration: " + ", ".join(missing))


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid config JSON at {path}: {exc}") from exc


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load_config(env: dict[str, str] | None = None, *, config_path: str | None = None) -> Config:
    env = env or os.environ
    path = Path(config_path or env.get("WORLD_ISSUES_CONFIG") or DEFAULT_CONFIG_PATH)
    file_config = _read_config_file(path)
    merged_env = dict(env)
    backend = merged_env.get("WORLD_ISSUES_BACKEND") or file_config.get("backend")
    if not backend:
        backend = "plane" if merged_env.get("PLANE_BASE_URL") or file_config.get("base_url") else "fake"
    return Config(
        base_url=merged_env.get("PLANE_BASE_URL") or file_config.get("base_url"),
        api_key=merged_env.get("PLANE_API_KEY") or file_config.get("api_key"),
        workspace=merged_env.get("WORLD_ISSUES_WORKSPACE") or file_config.get("workspace") or "acme",
        default_project=merged_env.get("WORLD_ISSUES_DEFAULT_PROJECT")
        or file_config.get("default_project")
        or "PAY",
        actor=merged_env.get("WORLD_ISSUES_ACTOR") or file_config.get("actor") or "agent",
        output=merged_env.get("WORLD_ISSUES_OUTPUT") or file_config.get("output") or "plain",
        backend=backend,
        state_file=Path(merged_env.get("WORLD_ISSUES_STATE_FILE") or file_config.get("state_file") or ".ticketvector/state.json"),
        config_path=path,
    )


def set_config_value(key: str, value: str, config: Config) -> dict[str, Any]:
    key_map = {
        "base-url": "base_url",
        "base_url": "base_url",
        "workspace": "workspace",
        "project": "default_project",
        "default-project": "default_project",
        "default_project": "default_project",
        "api-key": "api_key",
        "api_key": "api_key",
        "backend": "backend",
        "state-file": "state_file",
        "state_file": "state_file",
        "actor": "actor",
        "output": "output",
    }
    field = key_map.get(key)
    if not field:
        raise ConfigError(f"unsupported config key: {key}")
    current = _read_config_file(config.config_path)
    current[field] = value
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return replace(config, **{field: value}).redacted_dict()
