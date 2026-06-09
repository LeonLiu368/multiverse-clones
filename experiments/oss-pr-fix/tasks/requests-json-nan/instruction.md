# Fix: invalid JSON body sent when payload contains NaN/Infinity

You are an engineer at acme. A bug has been filed against the `requests`
library vendored into `acme/api-service`. Your job is to gather the context
from the issue tracker and team chat, implement the fix, and ship it as a pull
request whose code passes the test suite.

The required information is split across three surfaces — you will need all of
them:

## 1. Issue tracker — `linear`

```bash
linear issue mine                 # find the issue assigned to you
linear issue view API-202 --comments
```

The ticket names the symptom and the repository, and points you to the team
chat for the agreed implementation approach.

## 2. Team chat — `slack` (CLI or `slack-mcp` MCP server)

```bash
slack channels
slack history eng --limit 100
```

The `#eng` thread contains the root-cause diagnosis and the **exact**
implementation contract the team agreed on — the new exception's name, what it
must subclass, and how serialization must change. Read it carefully; the test
suite enforces that contract.

## 3. Code — `gh` / `git`

```bash
gh repo clone acme/api-service
cd api-service
python3 -m unittest discover -s tests -v   # existing tests (must keep passing)
```

## What to do

1. Read `API-202` in Linear and the `#eng` Slack thread to learn the exact fix.
2. Clone `acme/api-service` and implement the change in the source.
3. Make sure the existing tests in `tests/test_basic.py` still pass.
4. Commit on a new branch, push it, and open a **pull request against `main`**:

   ```bash
   git checkout -b fix/json-nan-validation
   git commit -am "fix: ..."
   git push -u origin fix/json-nan-validation
   gh pr create -R acme/api-service --base main --head fix/json-nan-validation \
     --title "..." --body "..."
   ```

Your work is graded by checking out your PR's branch and running the full test
suite (the existing tests plus additional hidden tests that exercise the bug).
All tests must pass.
