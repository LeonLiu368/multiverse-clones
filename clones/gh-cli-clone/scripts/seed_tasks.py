"""Reset + seed the forge repos the sample Harbor tasks operate on.

Operator setup (run before each harbor run for clean nop/oracle gates):
  uv run python scripts/seed_tasks.py
"""

from __future__ import annotations

import base64

from ghclone.config import resolve
from ghclone.forge import ForgejoClient, ForgejoError


def reset(c: ForgejoClient, name: str, *, auto_init: bool) -> None:
    try:
        c.delete_repo("ghc-admin", name)
    except ForgejoError:
        pass
    c.create_repo(name=name, description=f"sample task: {name}", auto_init=auto_init)


def main() -> None:
    c = ForgejoClient(resolve())

    # p0-open-issue: empty repo, agent files GHCTASK-OK
    reset(c, "harbortask", auto_init=False)

    # p1-triage: repo with one open issue to triage
    reset(c, "triage", auto_init=False)
    c.create_issue("ghc-admin", "triage", title="spammy issue", body="please triage")

    # p0-fix-pr: repo with a buggy calc.py on main + a bug report
    reset(c, "fixme", auto_init=True)
    c.put_file("ghc-admin", "fixme", "calc.py",
               content_b64=base64.b64encode(b"def div(a, b):\n    return a / b\n").decode(),
               message="add calc.py", branch="main")
    c.create_issue("ghc-admin", "fixme", title="div crashes on zero",
                   body="calc.py div(a, b) raises ZeroDivisionError when b == 0")
    print("seeded: harbortask, triage, fixme")


if __name__ == "__main__":
    main()
