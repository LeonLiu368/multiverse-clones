#!/usr/bin/env python3
"""Convert taskfarm-e2e-tasks from the OLD ticketvector + OLD slack services to our NEW
jira-gateway / slack-gateway clones (two-image + mount + service-DNS isolation model).

Only the slack + ticketvector pieces change. github / sentry / grafana / postgres / app / tests
logic stay intact. Idempotent-ish: operates on a fresh copy each run.
"""
import json, re, shutil, sys
from pathlib import Path
import yaml

SRC = Path("/tmp/multiverse-tasks-owen/taskfarm-e2e-tasks")
DST = Path("/Users/leonliu/projects/experiments-taskfarm/experiments/taskfarm-clones/tasks")

JIRA_IMG = "${JIRA_GATEWAY_IMAGE:-ghcr.io/abundant-ai/jira-gateway:empty}"
SLACK_IMG = "${SLACK_GATEWAY_IMAGE:-ghcr.io/abundant-ai/slack-gateway:empty}"

JIRA_HEALTHCHECK = {
    "test": ["CMD-SHELL",
             "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8765/health')\" || exit 1"],
    "interval": "5s", "timeout": "5s", "retries": 24, "start_period": "15s",
}

def project_key(task_dir: Path) -> str:
    sj = task_dir / "environment" / "data" / "ticketvector" / "state.json"
    if not sj.exists():
        return "ENG"
    issues = json.loads(sj.read_text()).get("issues", [])
    keys = sorted({(i.get("identifier", "") or "").split("-")[0] for i in issues if i.get("identifier")})
    return keys[0] if keys else "ENG"

def convert_compose(path: Path, proj: str):
    doc = yaml.safe_load(path.read_text())
    services = doc["services"]

    # --- ticketvector -> jira (rename key, drop netns sharing, add DNS hostname + healthcheck) ---
    tv = services.pop("ticketvector")
    jira = {
        "image": JIRA_IMG,
        "hostname": "jira",
        "platform": "linux/amd64",
        "environment": {
            "WORLD_ISSUES_STATE_FILE": "/var/lib/ticketvector/state.json",
            "WORLD_ISSUES_BIND_HOST": "0.0.0.0",
            "WORLD_ISSUES_PORT": "8765",
            "WORLD_ISSUES_ACTOR": "agent",
        },
        "volumes": ["./data/ticketvector/state.json:/var/lib/ticketvector/state.json:ro"],
        "healthcheck": dict(JIRA_HEALTHCHECK),
    }
    # rebuild services preserving original order, with `jira` where `ticketvector` was
    new_services = {}
    for k, v in services.items():
        new_services[k] = v
    # insert jira right after main for readability
    ordered = {}
    for k, v in new_services.items():
        ordered[k] = v
        if k == "main":
            ordered["jira"] = jira
    if "jira" not in ordered:
        ordered["jira"] = jira
    doc["services"] = ordered

    # --- main: repoint PLANE_BASE_URL to the DNS host + add remote/agent-mode env + depends_on jira ---
    main = doc["services"]["main"]
    env = main.setdefault("environment", {})
    if isinstance(env, list):  # normalize list-form env to dict
        env = dict(e.split("=", 1) for e in env)
        main["environment"] = env
    env["PLANE_BASE_URL"] = "http://jira:8765"
    env["WORLD_ISSUES_BACKEND"] = "remote"
    env["WORLD_ISSUES_AGENT_MODE"] = "1"
    env["WORLD_ISSUES_OUTPUT"] = "json"
    env["WORLD_ISSUES_ACTOR"] = "agent"
    env["WORLD_ISSUES_DEFAULT_PROJECT"] = proj
    dep = main.setdefault("depends_on", {})
    if isinstance(dep, list):
        dep = {d: {"condition": "service_started"} for d in dep}
        main["depends_on"] = dep
    dep["jira"] = {"condition": "service_healthy"}

    # --- slack-service -> slack-gateway (tbmq only); keep hostname + /data/mattermost mount ---
    if "slack" in doc["services"]:
        slack = doc["services"]["slack"]
        slack["image"] = SLACK_IMG

    path.write_text(
        "# Converted to the abundant clone format: ticketvector -> jira-gateway, slack-service ->\n"
        "# slack-gateway. Data lives ONLY in the sidecars (mounted, not on the agent FS); the agent\n"
        "# reaches them over HTTP at http://jira:8765 / http://slack via service-name DNS. No\n"
        "# network_mode/networks: blocks. See experiments/taskfarm-clones/README.md.\n"
        + yaml.safe_dump(doc, sort_keys=False, default_flow_style=False, width=100)
    )

def convert_dockerfile(path: Path, proj: str):
    if not path.exists():
        return False
    text = path.read_text()
    if "PLANE_BASE_URL=http://127.0.0.1:8765" not in text:
        return False
    text = text.replace(
        "PLANE_BASE_URL=http://127.0.0.1:8765",
        "PLANE_BASE_URL=http://jira:8765 WORLD_ISSUES_BACKEND=remote WORLD_ISSUES_AGENT_MODE=1 "
        "WORLD_ISSUES_OUTPUT=json WORLD_ISSUES_ACTOR=agent WORLD_ISSUES_DEFAULT_PROJECT=" + proj,
    )
    path.write_text(text)
    return True

def convert_tests(task_dir: Path):
    changed = []
    for p in (task_dir / "tests").rglob("*.py"):
        text = p.read_text()
        new = re.sub(
            r'\("http://127\.0\.0\.1:8765",\s*"http://main:8765"\)',
            '("http://jira:8765", "http://127.0.0.1:8765", "http://main:8765")',
            text,
        )
        if new != text:
            p.write_text(new)
            changed.append(p.name)
    return changed

def convert_solution(task_dir: Path):
    """The oracle solve.sh hits the tracker via raw RPC at the OLD address that only worked under
    network_mode: service:main. Re-point it at the jira sidecar DNS host, same as the verifier."""
    p = task_dir / "solution" / "solve.sh"
    if not p.exists():
        return False
    text = p.read_text()
    new = text.replace("http://127.0.0.1:8765", "http://jira:8765")
    if new != text:
        p.write_text(new)
        return True
    return False

def main():
    DST.mkdir(parents=True, exist_ok=True)
    for task in sorted(p for p in SRC.iterdir() if p.is_dir()):
        out = DST / task.name
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(task, out)
        proj = project_key(out)
        convert_compose(out / "environment" / "docker-compose.yaml", proj)
        df = convert_dockerfile(out / "environment" / "Dockerfile", proj)
        tests = convert_tests(out)
        sol = convert_solution(out)
        print(f"{task.name:42s} proj={proj:7s} dockerfile_env={df} tests={tests} solve.sh={sol}")

if __name__ == "__main__":
    main()
