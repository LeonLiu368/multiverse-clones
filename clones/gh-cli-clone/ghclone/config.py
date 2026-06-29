"""Runtime config for ghc.

Resolution order (highest first):
  1. explicit args / env: GHC_HOST, GHC_TOKEN
  2. config file under platformdirs user_config_dir/ghc/hosts.json
  3. defaults (localhost forge)

We intentionally mirror `gh`'s notion of a "host" so multi-instance support
drops in later, but default to the single local Forgejo.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

DEFAULT_HOST = "http://localhost:3300"
# Config lives under ~/.config/gh (real gh's dir), not ~/.config/ghc, so the
# on-disk surface looks native to an agent inspecting it.
CONFIG_DIR = Path(user_config_dir("gh"))
HOSTS_FILE = CONFIG_DIR / "hosts.json"


@dataclass
class HostConfig:
    host: str
    token: str | None
    user: str | None = None

    @property
    def api_base(self) -> str:
        return f"{self.host.rstrip('/')}/api/v1"


def _load_hosts() -> dict:
    if HOSTS_FILE.exists():
        try:
            return json.loads(HOSTS_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_host(host: str, token: str, user: str | None = None) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    hosts = _load_hosts()
    hosts[host] = {"token": token, "user": user}
    HOSTS_FILE.write_text(json.dumps(hosts, indent=2))


def resolve(host: str | None = None) -> HostConfig:
    # Prefer the same env vars real gh uses (GH_HOST/GH_TOKEN) so the runtime
    # surface is indistinguishable; keep GHC_* as a fallback for operator tools.
    host = host or os.getenv("GH_HOST") or os.getenv("GHC_HOST") or DEFAULT_HOST
    token = os.getenv("GH_TOKEN") or os.getenv("GHC_TOKEN")
    user = None
    if not token:
        # token-file fallback (used in the isolated multi-container layout: the
        # backend sidecar writes the token to a shared volume the agent box reads).
        token_file = os.getenv("GH_TOKEN_FILE") or os.getenv("GHC_TOKEN_FILE")
        for cand in (token_file, "/run/secrets/token", "/shared/token", "/etc/ghc/token"):
            if cand and Path(cand).exists():
                token = Path(cand).read_text().strip()
                break
    if not token:
        entry = _load_hosts().get(host, {})
        token = entry.get("token")
        user = entry.get("user")
    return HostConfig(host=host, token=token, user=user)
