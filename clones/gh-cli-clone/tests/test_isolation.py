"""R6.3 — agent isolation.

Asserts the agent under test is a sealed, data-free client: it reaches forge state
ONLY over HTTP and carries no seed/API/generator source it could read or recompute
the answer from. Per R2.k the leak rule is "grep is necessary but NOT sufficient",
so this checks all three:

  1. no on-disk forge state (the gateway's data dir is absent);
  2. `import ghclone` raises ModuleNotFoundError (no client/generator source);
  3. no api/ or seed/ source survives anywhere the agent can read.

Designed to run INSIDE the agent (`main`) container, wired into tests/test.sh —
that is where "the agent's view of the world" is the thing being asserted. When run
on a dev host where ghclone IS importable (the repo checkout), the import/source
checks are skipped with a clear reason so the suite stays green locally; the on-disk
state check always runs. The authoritative run is from a cold `docker compose up`.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Are we running inside the sealed agent, or on a dev host with the repo on PYTHONPATH?
_GHCLONE_IMPORTABLE = importlib.util.find_spec("ghclone") is not None
_IN_AGENT = os.path.exists("/usr/local/bin/gh") and not _GHCLONE_IMPORTABLE

# Where the gateway keeps forge state — must NEVER exist on the agent.
FORGE_STATE_PATHS = ["/var/lib/forgejo", "/shared/token", "/opt/ghclone"]

_agent_only = pytest.mark.skipif(
    _GHCLONE_IMPORTABLE,
    reason="ghclone importable here (dev checkout); the sealed-agent assertions run inside main via test.sh",
)


def test_no_forge_state_on_disk():
    """Always runs: the agent must carry no on-disk forge data dir / token."""
    for p in FORGE_STATE_PATHS:
        assert not os.path.exists(p), f"agent leak: forge state present at {p}"


@_agent_only
def test_import_ghclone_raises():
    """The clone's client/CLI/MCP source is not importable from the agent —
    so the agent cannot recompute the answer by importing a generator (R2.k #2)."""
    with pytest.raises(ModuleNotFoundError):
        __import__("ghclone")


@_agent_only
def test_no_api_or_seed_source_present():
    """No api/ or seed/ (or hydrate/generator) source dirs survive in the agent (R2.k #3)."""
    roots = ["/opt", "/app", "/usr/local"]
    offenders = []
    for root in roots:
        rp = Path(root)
        if not rp.exists():
            continue
        for pat in ("*/ghclone/forge/*", "*/ghclone/hydrate/*", "*/ghclone/mcp/*", "*/seed/*", "*/api/*"):
            offenders += [str(p) for p in rp.rglob(pat.split("/")[-1])
                          if "ghclone" in str(p) or "/seed/" in str(p)]
    assert not offenders, f"agent leak: clone source/generator present: {offenders[:5]}"


@_agent_only
def test_gh_is_a_sealed_binary_not_python_source():
    """`gh` on the agent is the compiled client, not a python entrypoint that could
    import the forge client package."""
    gh = "/usr/local/bin/gh"
    assert os.path.exists(gh)
    head = subprocess.run(["head", "-c", "4", gh], capture_output=True).stdout
    # ELF magic (PyInstaller onefile) — not a `#!/...python` shebang.
    assert head[:1] == b"\x7f" or head[:4] == b"\x7fELF", "gh is not a sealed compiled binary"


def test_isolation_context_is_known():
    """Smoke: we correctly classified the runtime (sealed agent vs dev host)."""
    assert _IN_AGENT or _GHCLONE_IMPORTABLE
