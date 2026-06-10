from workflow_assertions import assert_pr_merged, assert_successful_ci, run_gh, select_incident_pr

REPO = 'acme/oauth-qa-matrix'
ISSUE_ID = 'OPS-503'
BODY_TERMS = ['oauth', 'qa', 'matrix']
CHANGED_FILES = ['linking/coverage.py']
FORBIDDEN_PATH_PARTS = ("solution/", "data/ticketvector", "data/slack", "data/github", "seed.sh")

run_gh(["gh", "auth", "status"])
pr = select_incident_pr(REPO, ISSUE_ID, BODY_TERMS)
assert_pr_merged(pr)
assert_successful_ci(REPO, pr)
diff = run_gh(["gh", "pr", "diff", str(pr["number"]), "-R", REPO])
missing = [path for path in CHANGED_FILES if path not in diff]
forbidden = [part for part in FORBIDDEN_PATH_PARTS if part in diff]
assert not missing and not forbidden, {"pr": pr, "missing_changed_files": missing, "forbidden_paths": forbidden, "diff_head": diff[:2000]}
print("github PR checks passed")
