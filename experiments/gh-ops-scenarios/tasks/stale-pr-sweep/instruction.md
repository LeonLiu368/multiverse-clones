# Clean up stale pull requests in `acme/platform`

The `acme/platform` repository has several open pull requests. Some of them are
**stale** — their linked tracking issues have already been resolved without the PR
being merged, so the PR is no longer needed.

Your job:
- Review the open PRs and their linked issues.
- **Close any PR whose linked issue is already closed**, with a brief comment
  explaining why you're closing it.
- **Leave any PR whose linked issue is still open** — that work is still active.

You have `gh`. How you investigate and close them is up to you.

```bash
gh pr list -R acme/platform
gh issue list -R acme/platform --state all
gh issue view <number> -R acme/platform
```
