#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CAP = 8000
TESTS_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.environ.get("VERIFIER_LOG_DIR", "/logs/verifier"))
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    LOG_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "verifier"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

TASK_CONFIG = {
    "payment-retry-policy": {
        "repo": "acme/payment-retry-policy",
        "issue": "OPS-501",
        "artifact": "/app/artifacts/payment_retry_replay.json",
        "slack_query": "payment retry ready",
        "context_channels": ["payments-incidents"],
        "source_files": ["payments/retry_policy.py", "payments/webhooks.py", "payments/replay.py"],
    },
    "ledger-cutoff-window": {
        "repo": "acme/ledger-cutoff-window",
        "issue": "OPS-502",
        "artifact": "/app/artifacts/ledger_close_audit.json",
        "slack_query": "ledger cutoff ready",
        "context_channels": ["ledger-close"],
        "source_files": ["ledger/cutoff.py", "ledger/nightly_job.py", "ledger/replay.py"],
    },
    "oauth-qa-matrix": {
        "repo": "acme/oauth-qa-matrix",
        "issue": "OPS-503",
        "artifact": "/app/artifacts/oauth_linking_qa.json",
        "slack_query": "oauth qa matrix ready",
        "context_channels": ["oauth-rollout"],
        "source_files": ["linking/coverage.py", "linking/replay.py"],
    },
    "duplicate-account-guard": {
        "repo": "acme/duplicate-account-guard",
        "issue": "OPS-504",
        "artifact": "/app/artifacts/account_dedupe_audit.json",
        "slack_query": "duplicate account guard ready",
        "context_channels": ["account-integrity", "data"],
        "source_files": ["accounts/dedupe.py", "accounts/replay.py"],
    },
}


def truncate(value, cap=CAP):
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    if len(text) <= cap:
        return text
    return text[:cap] + "\n...<truncated>"


def read_text(path, cap=CAP):
    try:
        return {"status": "ok", "path": str(path), "content": truncate(Path(path).read_text(errors="replace"), cap)}
    except FileNotFoundError:
        return {"status": "missing", "path": str(path)}
    except Exception as exc:
        return {"status": "error", "path": str(path), "error": str(exc)}


def run_cmd(cmd, cwd=None, timeout=10, input_text=None, cap=CAP):
    env = os.environ.copy()
    env.setdefault("GH_HOST", "http://github")
    env.setdefault("GH_TOKEN_FILE", "/run/secrets/token")
    env["PYTHONPATH"] = "/app/src:{}{}".format(TESTS_DIR / "deterministic", ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    record = {"cmd": cmd, "cwd": str(cwd) if cwd else None, "status": "error"}
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        record.update(
            {
                "status": "ok" if proc.returncode == 0 else "failed",
                "returncode": proc.returncode,
                "stdout_excerpt": truncate(proc.stdout, cap),
                "stderr_excerpt": truncate(proc.stderr, cap),
            }
        )
    except FileNotFoundError as exc:
        record.update({"status": "unavailable", "returncode": None, "error": str(exc)})
    except subprocess.TimeoutExpired as exc:
        record.update(
            {
                "status": "timeout",
                "returncode": None,
                "stdout_excerpt": truncate(exc.stdout or ""),
                "stderr_excerpt": truncate(exc.stderr or ""),
                "error": "timeout",
            }
        )
    except Exception as exc:
        record.update({"status": "error", "returncode": None, "error": str(exc)})
    return record


def load_task_slug():
    for path in (TESTS_DIR / "rubric.json",):
        try:
            task = json.loads(path.read_text()).get("task")
            if task:
                return str(task)
        except Exception:
            pass
    if TESTS_DIR.parent.name in TASK_CONFIG:
        return TESTS_DIR.parent.name
    name = os.environ.get("TASK_SLUG")
    if name:
        return name
    return "unknown"


def task_root_candidates():
    return [
        TESTS_DIR.parent,
        Path("/"),
        Path("/task"),
        Path("/app/task"),
    ]


def find_task_file(name):
    for root in task_root_candidates():
        path = root / name
        if path.exists():
            return path
    return TESTS_DIR.parent / name


def collect_git(config):
    app = Path("/app/src")
    result = {"status": "missing", "path": str(app)}
    if not app.exists():
        return result
    # verifier runs as root against the agent-owned repo; without this every
    # git command fails with "detected dubious ownership"
    run_cmd(["git", "config", "--global", "--add", "safe.directory", "*"], timeout=5)
    result = {
        "branch": run_cmd(["git", "branch", "--show-current"], cwd=app),
        "head_commit": run_cmd(["git", "show", "--stat", "--patch", "--no-color", "HEAD"], cwd=app, timeout=20),
        "status": run_cmd(["git", "status", "--porcelain=v1"], cwd=app),
        "remote": run_cmd(["git", "remote", "-v"], cwd=app),
        "recent_log": run_cmd(["git", "log", "--oneline", "--decorate", "-8"], cwd=app),
        "diff_stat": run_cmd(["git", "diff", "--stat"], cwd=app),
        "diff_name_status": run_cmd(["git", "diff", "--name-status"], cwd=app),
    }
    snippets = {}
    for rel in config.get("source_files", []):
        snippets[rel] = {
            "worktree_file": read_text(app / rel, 6000),
            "diff": run_cmd(["git", "diff", "--", rel], cwd=app, timeout=20),
        }
    result["source_snippets"] = snippets
    return result


def collect_artifacts(config):
    artifact_dir = Path("/app/artifacts")
    result = {"directory": str(artifact_dir), "files": []}
    if artifact_dir.exists():
        for path in sorted(artifact_dir.glob("*"))[:40]:
            item = {"path": str(path), "size": path.stat().st_size if path.is_file() else None}
            if path.is_file() and path.suffix.lower() == ".json":
                try:
                    item["json"] = json.loads(path.read_text())
                except Exception as exc:
                    item["json_error"] = str(exc)
                    item["content"] = read_text(path)
            elif path.is_file():
                item["content"] = read_text(path, 4000)
            result["files"].append(item)
    else:
        result["status"] = "missing"
    expected = config.get("artifact")
    if expected:
        result["expected_artifact"] = read_text(expected)
        try:
            result["expected_artifact_json"] = json.loads(Path(expected).read_text())
        except Exception as exc:
            result["expected_artifact_json_error"] = str(exc)
    return result


def collect_github(config):
    repo = config.get("repo")
    if not repo:
        return {"status": "unknown_repo"}
    result = {
        "auth_status": run_cmd(["gh", "auth", "status"], timeout=8),
        "pr_list": run_cmd(
            [
                "gh",
                "pr",
                "list",
                "-R",
                repo,
                "--state",
                "all",
                "--json",
                "number,title,headRefName,body,url,state,merged,mergedAt,headRefOid",
            ],
            timeout=12,
        ),
        "run_list": run_cmd(
            ["gh", "run", "list", "-R", repo, "--json", "number,name,displayTitle,status,conclusion,headBranch,workflowName,createdAt"],
            timeout=12,
        ),
    }
    # gh pr diff requires an explicit PR number; resolve numbers first, then
    # capture the diff of each PR so the judge can verify scope directly
    listing = run_cmd(["gh", "pr", "list", "-R", repo, "--state", "all", "--json", "number"], timeout=12)
    pr_numbers = []
    try:
        pr_numbers = sorted(int(item["number"]) for item in json.loads(listing.get("stdout_excerpt") or "[]"))
    except Exception as exc:
        result["pr_numbers_error"] = str(exc)
    result["pr_diffs"] = {
        str(number): run_cmd(["gh", "pr", "diff", str(number), "-R", repo], timeout=15)
        for number in pr_numbers[-5:]
    }
    return result


def collect_ticket(config):
    issue = config.get("issue")
    if not issue:
        return {"status": "unknown_issue"}
    # `issue view --comments --links --attachments` is the only way the CLI
    # exposes comment bodies; a bare `issue view` only returns comments_count
    return {
        "linear_help": run_cmd(["linear", "--help"], timeout=10),
        "linear_issue": run_cmd(
            ["linear", "issue", "view", issue, "--comments", "--links", "--attachments", "--json"], timeout=8, cap=16000
        ),
        "jira_help": run_cmd(["jira", "--help"], timeout=10),
        "jira_issue": run_cmd(
            ["jira", "issue", "view", issue, "--comments", "--links", "--attachments", "--json"], timeout=8, cap=16000
        ),
    }


def collect_slack(config):
    query = config.get("slack_query") or config.get("issue") or ""
    issue = config.get("issue") or ""
    result = {
        "query": query,
        # Full handoff-channel history is the primary evidence: agents may word the
        # handoff naturally, so phrase searches alone must never decide this.
        "handoff_channel_history": run_cmd(
            ["slack", "--json", "history", "incident-updates", "--limit", "50"], timeout=8
        ),
        # the incident context thread(s) are trusted background for the judge:
        # they let it verify recovered-policy claims directly
        "context_channel_history": {
            channel: run_cmd(["slack", "--json", "history", channel, "--limit", "50"], timeout=8)
            for channel in config.get("context_channels", [])
        },
        "cli_search": run_cmd(["slack", "search", query], timeout=8) if query else {"status": "skipped"},
        "issue_search": run_cmd(["slack", "search", issue], timeout=8) if issue else {"status": "skipped"},
    }
    api_base = os.environ.get("SLACK_API_URL", "http://slack").rstrip("/")
    token = os.environ.get("SLACK_BOT_TOKEN", "test-token-acme-eval")
    history_data = urllib.parse.urlencode({"channel": "incident-updates", "limit": "50"}).encode()
    history_req = urllib.request.Request(
        api_base + "/api/conversations.history",
        data=history_data,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(history_req, timeout=2) as response:
            result["api_channel_history"] = {"status": "ok", "response": json.loads(response.read().decode())}
    except Exception as exc:
        result["api_channel_history"] = {"status": "error", "error": str(exc)}
    api = os.environ.get("SLACK_API_URL", "http://slack").rstrip("/") + "/api/search.messages"
    token = os.environ.get("SLACK_BOT_TOKEN", "test-token-acme-eval")
    if not query:
        return result
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(
        api,
        data=data,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    last_error = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                payload = json.loads(response.read().decode())
            result["api_search"] = {"status": "ok", "response": payload}
            return result
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.2)
    result["api_search"] = {"status": "error", "error": last_error}
    return result


def collect_deterministic_checks():
    deterministic = TESTS_DIR / "deterministic"
    checks = ["test_hidden.py", "check_artifact.py", "check_github.py", "check_ticket_state.py", "check_slack.py"]
    results = {}
    cwd = Path("/app/src") if Path("/app/src").exists() else None
    for check in checks:
        path = deterministic / check
        if path.exists():
            results[check] = run_cmd([sys.executable, str(path)], cwd=cwd, timeout=90)
        else:
            results[check] = {"status": "missing", "path": str(path)}
    return results


def collect_transcript():
    logs = Path("/logs")
    if not logs.exists():
        return {"status": "unavailable", "path": str(logs)}
    files = []
    for path in sorted(logs.rglob("*")):
        if not path.is_file() or str(path).startswith(str(LOG_DIR)):
            continue
        lowered = path.name.lower()
        if any(token in lowered for token in ("trajectory", "rollout", "transcript", "agent", "jsonl", "log")):
            files.append(read_text(path, 6000))
        if len(files) >= 10:
            break
    return {"status": "ok", "files": files} if files else {"status": "unavailable", "path": str(logs)}


def main():
    task = load_task_slug()
    config = TASK_CONFIG.get(task, {})
    evidence = {
        "schema_version": 1,
        "task": task,
        "task_config": config,
        "instruction": read_text(find_task_file("instruction.md")),
        "task_toml": read_text(find_task_file("task.toml")),
        "rubric": read_text(TESTS_DIR / "rubric.json"),
        "git": collect_git(config),
        "artifacts": collect_artifacts(config),
        "github": collect_github(config),
        "ticketvector": collect_ticket(config),
        "slack": collect_slack(config),
        "agent_transcript": collect_transcript(),
        "deterministic_check_results": collect_deterministic_checks(),
    }
    (LOG_DIR / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        fallback = {"schema_version": 1, "status": "collector_error", "error": str(exc)}
        (LOG_DIR / "evidence.json").write_text(json.dumps(fallback, indent=2, sort_keys=True) + "\n")
        raise
