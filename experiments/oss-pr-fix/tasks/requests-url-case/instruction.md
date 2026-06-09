# Pull request review — case-insensitive URL scheme matching

A bug was reported in the `requests` library vendored into `acme/webapp`:
HTTP adapters silently fail when URLs use uppercase schemes such as
`HTTP://example.com` or `HTTPS://example.com`.

RFC 2396 §3.1 requires scheme names to be treated as case-insensitive —
`HTTP` and `http` are the same scheme. The current code calls
`url.startswith('https')` and `url.startswith(prefix)` directly, so
uppercase-scheme URLs bypass SSL certificate verification and adapter selection.

A fix has been submitted as an open pull request. Your job is to inspect the
proposed change, verify it correctly normalizes URL schemes before every
scheme-sensitive comparison, then approve and merge it.

## Code — `gh` / `git`

```bash
# list open PRs
gh pr list -R acme/webapp

# read the PR description and diff
gh pr view 1 -R acme/webapp
gh pr diff 1 -R acme/webapp

# optionally clone to inspect file history
gh repo clone acme/webapp
```

## What to do

Review the diff. Confirm that `.lower()` (or equivalent) is applied before
every `startswith()` call that checks URL schemes in both
`requests/adapters.py` and `requests/sessions.py`. If the fix looks correct,
approve and merge the PR.

```bash
gh pr review 1 -R acme/webapp --approve -b "LGTM"
gh pr merge 1 -R acme/webapp --squash
```
