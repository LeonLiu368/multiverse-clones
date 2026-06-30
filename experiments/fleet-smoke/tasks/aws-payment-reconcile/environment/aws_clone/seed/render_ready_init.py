from __future__ import annotations


def render_ready_init() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
python -m aws_clone.seed.wait_ready
python -m aws_clone.seed.load_state
"""


def main() -> int:
    print(render_ready_init(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
