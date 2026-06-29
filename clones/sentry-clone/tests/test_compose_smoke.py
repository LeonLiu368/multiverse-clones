from __future__ import annotations

import os
import shutil
import subprocess


def test_compose_smoke() -> None:
    if os.environ.get("SENTRY_CLONE_RUN_DOCKER_SMOKE") != "1":
        return
    if not shutil.which("docker"):
        return
    subprocess.run(["docker", "build", "-f", "Dockerfile.service", "-t", "sentry-clone-service:local", "."], check=True, timeout=180)
    subprocess.run(["docker", "compose", "-f", "examples/docker-compose.yaml", "up", "-d"], check=True, timeout=120)
    try:
        env = os.environ.copy()
        env.update({"SENTRY_URL": "http://localhost:3000", "SENTRY_AUTH_TOKEN": "test-token-acme-eval", "SENTRY_CLONE_ADMIN_TOKEN": "test-admin-token-acme-eval"})
        subprocess.run(["curl", "-sf", "http://localhost:3000/api/healthz"], check=True, timeout=10)
        subprocess.run(["bin/sentry", "whoami", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/sentry", "issues", "list", "--project", "payments-api", "--query", "is:unresolved", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/sentry", "issues", "stacktrace", "PAYMENTS-501", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/sentry", "issues", "breadcrumbs", "PAYMENTS-501", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/sentry", "issues", "suspect-commits", "PAYMENTS-501", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/sentry", "issues", "comment", "PAYMENTS-501", "--text", "compose smoke", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/sentry", "issues", "resolve", "PAYMENTS-501", "--in-release", "payments-api@2026.06.07.2", "--json"], env=env, check=True, timeout=10)
        subprocess.run(["bin/sentry-clonectl", "mutations"], env=env, check=True, timeout=10)
    finally:
        subprocess.run(["docker", "compose", "-f", "examples/docker-compose.yaml", "down", "-v"], check=False, timeout=60)
