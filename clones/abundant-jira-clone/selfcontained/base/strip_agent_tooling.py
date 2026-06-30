#!/usr/bin/env python3
"""Strip the ticketvector gateway's API + world-building source from the AGENT image (R2.k).

The agent runs the `jira`/`linear`/`world-issues` CLI as a thin HTTP client of the
`jira` sidecar (`WORLD_ISSUES_BACKEND=remote`, `WORLD_ISSUES_AGENT_MODE=1`). In that mode
the CLI only ever talks to the sidecar's `/rpc` API — it never serves the API itself and
never builds a world. But the upstream `world_issues` package ships those capabilities as
modules that `cli.py` imports at load time:

  * server.py    — the gateway HTTP API (the agent must never serve state)
  * seed.py      — the synthetic-world *generator* (the leak the audit named:
                   `import world_issues.seed` was importable in the agent)
  * plane.py     — the real-Plane provisioning/bootstrap adapter
  * demo.py      — the canned demo-world builder
  * runtime.py   — the task grader / redactor / agent-env writer
  * snapshot.py  — state snapshot/diff (world capture)

Per Clone Standard R2.k / R6.3, none of that source may survive in the agent, and
`import world_issues.seed` must raise `ModuleNotFoundError`. A literal-grep being clean is
NOT sufficient — a *generator* the agent can import and re-run is itself the leak.

This script, run at agent build time, surgically:
  1. rewrites the top-level imports of those modules in cli.py to no-ops, and rewrites the
     handlers that use them to raise `UnsupportedCommandError` (those subcommands are
     already blocked by WORLD_ISSUES_AGENT_MODE=1, so the agent loses nothing reachable);
  2. deletes the six module files outright.

What REMAINS is exactly the remote thin-client surface: cli.py (patched), client.py's
RPC transport, config/errors/manifest/models/output/git/jql/resolver. The corpus DB was
never in this package — it lives only in the sidecar — so after this the agent can neither
read nor regenerate any world.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PKG = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/ticketvector/world_issues")

DANGEROUS_MODULES = ["server", "seed", "plane", "demo", "runtime", "snapshot"]

# Any top-level `from .<mod> import a, b as c, ...` for a dangerous module must go. We rewrite
# each such line so the imported NAMES are bound to a raising shim instead — so the module body
# can be deleted while cli.py still imports cleanly. This is regex-driven (tolerant of upstream
# whitespace / argument-list changes) rather than exact-string matched.
IMPORT_RE = re.compile(
    r"^from \.(?:" + "|".join(DANGEROUS_MODULES) + r") import (?P<names>.+)$",
    re.M,
)


def _bound_names(names: str) -> list[str]:
    """Extract the bound local names from an import list ('a, b as c' -> ['a', 'c'])."""
    bound = []
    for piece in names.split(","):
        piece = piece.strip()
        if not piece:
            continue
        bound.append(piece.split(" as ")[-1].strip())
    return bound

# The shim function, injected BEFORE the first rewritten import so the rewritten
# `name = name = _agent_disabled` assignments can reference it.
SHIM = (
    "def _agent_disabled(*_a, **_k):\n"
    "    raise RuntimeError(\n"
    "        'this command is disabled in the agent image (remote thin-client only)'\n"
    "    )\n\n\n"
)


def patch_cli(cli_path: Path) -> None:
    text = cli_path.read_text(encoding="utf-8")

    def _replace(match: "re.Match[str]") -> str:
        names = _bound_names(match.group("names"))
        return " = ".join(names) + " = _agent_disabled"

    # Neutralize the indented lazy `from .runtime import write_agent_env` too (it lives inside
    # the agent-mode-blocked `runtime agent-env` handler, but the module is being deleted).
    text = re.sub(
        r"^(?P<indent>\s+)from \.runtime import write_agent_env\s*$",
        r"\g<indent>write_agent_env = _agent_disabled",
        text,
        flags=re.M,
    )

    new_text, n = IMPORT_RE.subn(_replace, text)
    if n == 0:
        raise SystemExit("no dangerous `from .<mod> import` lines found in cli.py (upstream changed?)")
    text = new_text

    # Inject the shim ONCE, immediately before the first `from .` (package-relative) import so the
    # rewritten `name = name = _agent_disabled` lines can reference _agent_disabled.
    first_rel = re.search(r"^from \.", text, flags=re.M)
    if not first_rel:
        raise SystemExit("no package-relative import found; cannot inject agent shim safely")
    idx = first_rel.start()
    text = text[:idx] + SHIM + text[idx:]
    # The lone agent-reachable use of a stubbed symbol: `save_receipt(receipt)` in the
    # `issue pr` dry-run path. Drop the call (the receipt is still returned).
    text = re.sub(r"^\s*save_receipt\(receipt\)\s*$", "", text, flags=re.M)
    cli_path.write_text(text, encoding="utf-8")


def main() -> None:
    cli = PKG / "cli.py"
    if not cli.exists():
        raise SystemExit(f"cli.py not found under {PKG}")
    patch_cli(cli)
    removed = []
    for mod in DANGEROUS_MODULES:
        target = PKG / f"{mod}.py"
        if target.exists():
            target.unlink()
            removed.append(target.name)
    print(f"[strip_agent_tooling] patched cli.py; removed: {', '.join(removed) or '(none)'}")


if __name__ == "__main__":
    main()
