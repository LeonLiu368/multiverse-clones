import json
import os
import re
import subprocess
import time
from pathlib import Path


def run_gh(cmd):
    env = os.environ.copy()
    env.setdefault("GH_HOST", "http://github")
    env.setdefault("GH_TOKEN_FILE", "/run/secrets/token")
    last = None
    for _ in range(40):
        proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
        if proc.returncode == 0:
            return proc.stdout
        last = proc.stderr or proc.stdout
        time.sleep(0.5)
    raise AssertionError({"cmd": cmd, "last": last})


def try_gh_json(cmd):
    try:
        out = run_gh(cmd)
        return json.loads(out or "[]")
    except AssertionError:
        return []


def pr_text(pr):
    return " ".join(str(pr.get(k) or "") for k in ("headRefName", "title", "body", "url", "state")).lower()


def list_pull_requests(repo):
    fields = "number,title,headRefName,body,url,state,merged,mergedAt,headRefOid"
    by_number = {}
    for state in ("open", "merged", "closed", "all"):
        for pr in try_gh_json(["gh", "pr", "list", "-R", repo, "--state", state, "--json", fields]):
            if pr.get("number") is not None:
                by_number[str(pr["number"])] = pr
    return list(by_number.values())


def select_incident_pr(repo, issue_id, body_terms=None):
    # Keep body_terms for call-site compatibility. The PR itself only needs to identify
    # the incident; artifact, Slack, ticket, CI, and merge evidence are checked separately.
    prs = list_pull_requests(repo)
    matches = []
    failures = []
    for pr in prs:
        text = pr_text(pr)
        if issue_id.lower() in text:
            matches.append(pr)
        else:
            failures.append({"pr": pr, "missing": ["issue_id"]})
    if not matches:
        raise AssertionError({"prs": prs, "failures": failures})
    matches.sort(key=lambda pr: (not is_merged_pr(pr), int(pr.get("number") or 0)))
    selected = matches[0]
    Path(f"/tmp/{issue_id.lower()}_selected_pr.json").write_text(json.dumps(selected, sort_keys=True))
    return selected


def is_merged_pr(pr):
    state = str(pr.get("state") or "").lower()
    return bool(pr.get("merged")) or state == "merged" or bool(pr.get("mergedAt"))


def assert_pr_merged(pr):
    assert is_merged_pr(pr), {"pr_not_merged": pr}


def assert_successful_ci(repo, pr):
    branch = str(pr.get("headRefName") or "")
    fields = "number,name,displayTitle,status,conclusion,headBranch,workflowName,createdAt"
    runs = try_gh_json(["gh", "run", "list", "-R", repo, "--json", fields])
    successes = []
    for run in runs:
        status = str(run.get("status") or run.get("conclusion") or "").lower()
        conclusion = str(run.get("conclusion") or "").lower()
        run_branch = str(run.get("headBranch") or "")
        branch_matches = branch and run_branch == branch
        if branch_matches and (status == "success" or conclusion == "success"):
            successes.append(run)
    assert successes, {"branch": branch, "runs": runs[:10]}


def pr_reference_matches(text, pr, repo):
    value = str(text or "").lower()
    url = str(pr.get("url") or "").lower()
    number = str(pr.get("number") or "")
    repo_lower = repo.lower()
    repo_tail = repo_lower.split("/", 1)[-1]
    if url and url in value:
        return True
    if number:
        path = f"{repo_lower}/pull/{number}"
        if path in value:
            return True
        if f"/{repo_tail}/pull/{number}" in value:
            return True
        if re.search(rf"\b(pr|pull request)\s*#?\s*{re.escape(number)}\b", value) and repo_tail in value:
            return True
    return False


def any_pr_reference(values, pr, repo):
    return any(pr_reference_matches(value, pr, repo) for value in values)
