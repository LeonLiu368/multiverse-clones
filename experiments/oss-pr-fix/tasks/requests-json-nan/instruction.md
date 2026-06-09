# Pull request review — reject NaN/Infinity in JSON request bodies

A bug was reported in the `requests` library vendored into `acme/api-service`:
sending a JSON payload that contains `float('nan')` or `float('inf')` silently
produces an invalid JSON body.

RFC 4627 §2.4 requires that JSON numeric values be finite. Python's
`json.dumps` emits `NaN` and `Infinity` by default — valid JavaScript, but not
valid JSON. Most HTTP servers (and strict JSON parsers) respond with a 400 Bad
Request, making the failure hard to trace back to the serialization layer.

A fix that raises a new `InvalidJSONError` exception has been submitted as an
open pull request. Your job is to inspect the proposed change, verify it
correctly guards `json.dumps` and adds the exception class, then approve and
merge it.

## Code — `gh` / `git`

```bash
# list open PRs
gh pr list -R acme/api-service

# read the PR description and diff
gh pr view 1 -R acme/api-service
gh pr diff 1 -R acme/api-service

# optionally clone to inspect file history
gh repo clone acme/api-service
```

## What to do

Review the diff. Confirm that:

1. `requests/exceptions.py` adds `InvalidJSONError` as a subclass of `RequestException`.
2. `requests/models.py` passes `allow_nan=False` to `json.dumps` and raises
   `InvalidJSONError` on `ValueError`.

If the fix looks correct, approve and merge the PR.

```bash
gh pr review 1 -R acme/api-service --approve -b "LGTM"
gh pr merge 1 -R acme/api-service --squash
```
