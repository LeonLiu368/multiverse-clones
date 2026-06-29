from __future__ import annotations

import json
import sys
from typing import Any


def emit_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def error(message: str) -> None:
    print(f"aws-clonectl: {message}", file=sys.stderr)
