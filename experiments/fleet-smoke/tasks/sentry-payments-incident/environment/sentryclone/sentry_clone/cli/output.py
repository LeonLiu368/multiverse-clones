from __future__ import annotations

import json
import sys
from typing import Any


def emit_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def emit_table(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                print("  ".join(str(item.get(key, "")) for key in ("shortId", "id", "slug", "name", "title", "status") if key in item))
            else:
                print(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
        return
    print(value)


def error(message: str) -> None:
    print(f"sentry: error: {message}", file=sys.stderr)
