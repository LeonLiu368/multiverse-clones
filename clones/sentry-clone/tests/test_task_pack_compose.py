from __future__ import annotations

import os
import shutil
import subprocess


COMPOSE = ["docker", "compose", "-f", "examples/task-pack-compose/docker-compose.yaml"]


def test_task_pack_compose_smoke() -> None:
    if os.environ.get("SENTRY_CLONE_RUN_DOCKER_SMOKE") != "1":
        return
    if not shutil.which("docker"):
        return
    subprocess.run(["docker", "build", "-f", "Dockerfile.service", "-t", "sentry-clone-service:local", "."], check=True, timeout=180)
    subprocess.run([*COMPOSE, "up", "-d", "--build"], check=True, timeout=180)
    try:
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "test", "!", "-e", "/data/sentry-clone/state.json"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "sh", "-lc", "command -v sentry && command -v sentry-mcp && ! command -v sentry-clonectl"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "sentry", "issues", "list", "--project", "payments-api", "--query", "is:unresolved", "--json"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "sentry", "issues", "stacktrace", "PAYMENTS-501", "--json"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "sentry", "issues", "breadcrumbs", "PAYMENTS-501", "--json"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "sentry", "issues", "comment", "PAYMENTS-501", "--text", "task-pack smoke comment", "--json"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "-e", "SENTRY_URL=http://localhost", "-e", "SENTRY_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval", "sentry", "sentry-clonectl", "mutations"], check=True, timeout=10)
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False, timeout=60)
