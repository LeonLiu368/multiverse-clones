from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def wait_ready(endpoint_url: str | None = None, timeout_seconds: int | None = None) -> dict[str, object]:
    endpoint = (endpoint_url or os.environ.get("AWS_ENDPOINT_URL") or "http://localhost:4566").rstrip("/")
    timeout = timeout_seconds or int(os.environ.get("AWS_CLONE_LOCALSTACK_READY_TIMEOUT", "90"))
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{endpoint}/_localstack/health", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
                services = payload.get("services", {})
                if not services or any(value in ("available", "running") for value in services.values()):
                    return {"ok": True, "endpoint_url": endpoint, "health": payload}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise TimeoutError(f"LocalStack did not become ready at {endpoint}: {last_error}")


def main() -> int:
    try:
        print(json.dumps(wait_ready(), sort_keys=True))
        return 0
    except Exception as exc:
        print(f"aws-clone: LocalStack readiness failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
