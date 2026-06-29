from __future__ import annotations

import os
import shutil
import subprocess


COMPOSE = ["docker", "compose", "-f", "examples/task-pack-compose/docker-compose.yaml"]


def test_task_pack_compose_smoke() -> None:
    if os.environ.get("GAUGE_RUN_DOCKER_SMOKE") != "1":
        return
    if not shutil.which("docker"):
        return

    subprocess.run(["docker", "build", "-f", "Dockerfile.service", "-t", "gauge-service:local", "."], check=True, timeout=180)
    subprocess.run([*COMPOSE, "up", "-d", "--build"], check=True, timeout=180)
    try:
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "test", "!", "-e", "/data/gauge/state.json"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "sh", "-lc", "command -v gcx && command -v mcp-grafana && ! command -v gaugectl"], check=True, timeout=10)
        subprocess.run([*COMPOSE, "exec", "-T", "agent", "gcx", "dashboards", "search", "payment", "--json"], check=True, timeout=10)
        subprocess.run(
            [
                *COMPOSE,
                "exec",
                "-T",
                "agent",
                "gcx",
                "metrics",
                "query",
                "-d",
                "prom-payments",
                'sum by (status_code)(increase(payment_gateway_responses_total{service="payments"}[5m]))',
                "--since",
                "1h",
                "--step",
                "5m",
                "--json",
            ],
            check=True,
            timeout=10,
        )
        subprocess.run(
            [*COMPOSE, "exec", "-T", "agent", "gcx", "logs", "query", "-d", "loki-payments", '{service="payments"} |= "lock_conflict"', "--since", "1h", "--limit", "20", "--json"],
            check=True,
            timeout=10,
        )
        subprocess.run(
            [
                *COMPOSE,
                "exec",
                "-T",
                "agent",
                "gcx",
                "annotations",
                "create",
                "--dashboard",
                "dash-payment-webhooks",
                "--panel",
                "1",
                "--text",
                "task-pack smoke annotation",
                "--tags",
                "smoke,TASK-PACK",
                "--json",
            ],
            check=True,
            timeout=10,
        )
        subprocess.run(
            [*COMPOSE, "exec", "-T", "-e", "GRAFANA_URL=http://localhost", "-e", "GAUGE_ADMIN_TOKEN=test-admin-token-acme-eval", "gauge", "gaugectl", "mutations"],
            check=True,
            timeout=10,
        )
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False, timeout=60)
