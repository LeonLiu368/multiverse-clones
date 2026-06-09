# Fix: uppercase URL schemes fail adapter selection

You are an engineer at acme. A bug has been filed against the `requests`
library vendored into `acme/webapp`. Your job is to gather the context from
the issue tracker and team chat, implement the fix, and ship it as a pull
request whose code passes the test suite.

The required information is split across three surfaces — you will need all of
them:

## 1. Issue tracker — `linear`

```bash
linear issue mine                 # find the issue assigned to you
linear issue view WEB-101 --comments
```

The ticket names the symptom and the repository, and points you to the team
chat for the agreed implementation approach.

## 2. Team chat — `slack` (CLI or `slack-mcp` MCP server)

```bash
slack channels
slack history eng --limit 100
```

The `#eng` thread contains the root-cause diagnosis and the **exact**
implementation contract the team agreed on — which functions must change and
how. Read it carefully; the test suite enforces that contract.

## 3. Code — `gh` / `git`

```bash
gh repo clone acme/webapp
cd webapp
python3 -m unittest discover -s tests -v   # existing tests (must keep passing)
```

## What to do

1. Read `WEB-101` in Linear and the `#eng` Slack thread to learn the exact fix.
2. Clone `acme/webapp` and implement the change in the source.
3. Make sure the existing tests in `tests/test_basic.py` still pass.
4. Commit on a new branch, push it, and open a **pull request against `main`**:

   ```bash
   git checkout -b fix/uppercase-url-scheme
   git commit -am "fix: ..."
   git push -u origin fix/uppercase-url-scheme
   gh pr create -R acme/webapp --base main --head fix/uppercase-url-scheme \
     --title "..." --body "..."
   ```

Your work is graded by checking out your PR's branch and running the full test
suite (the existing tests plus additional hidden tests that exercise the bug).
All tests must pass.
