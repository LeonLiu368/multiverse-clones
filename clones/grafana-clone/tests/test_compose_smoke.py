from __future__ import annotations

import os
import shutil
import subprocess


def test_compose_smoke() -> None:
    if os.environ.get("GRAFANA_RUN_DOCKER_SMOKE") != "1":
        return
    if not shutil.which("docker"):
        return
    subprocess.run(["docker", "build", "-f", "Dockerfile.service", "-t", "grafana-service:local", "."], check=True, timeout=180)
    subprocess.run(["docker", "compose", "-f", "examples/docker-compose.yaml", "up", "-d"], check=True, timeout=120)
    try:
        subprocess.run(["curl", "-sf", "http://localhost:3000/api/healthz"], check=True, timeout=10)
        env = os.environ.copy()
        env.update(
            {
                "GRAFANA_URL": "http://localhost:3000",
                "GRAFANA_TOKEN": "test-token-acme-eval",
                "GRAFANA_ADMIN_TOKEN": "test-admin-token-acme-eval",
            }
        )
        subprocess.run(["bin/gcx", "whoami", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/gcx", "dashboards", "search", "payment", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/gcx", "metrics", "query", "-d", "prom-payments", 'sum by (status_code)(increase(payment_gateway_responses_total{service="payments"}[5m]))', "--since", "1h", "--step", "5m", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/gcx", "logs", "query", "-d", "loki-payments", '{service="payments"} |= "lock_conflict"', "--since", "1h", "--limit", "20", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/gcx", "annotations", "create", "--dashboard", "dash-payment-webhooks", "--panel", "1", "--text", "compose smoke", "--tags", "smoke,COMPOSE", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/grafanactl", "mutations"], env=env, check=True, timeout=10)
    finally:
        subprocess.run(["docker", "compose", "-f", "examples/docker-compose.yaml", "down", "-v"], check=False, timeout=60)
