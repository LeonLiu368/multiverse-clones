# Release blocker in `acme/billing`

There is an open release-blocker issue in the `acme/billing` repository. The bug
is on the `release-v1.1` branch — **not on `main`** (main was already fixed).

Your job:
1. Find the blocker issue and understand the bug.
2. Fix `billing.py` on the `release-v1.1` branch.
3. Ship the fix via a pull request **targeting `release-v1.1`** (not main), get it
   reviewed, and merge it.
4. Cut a `v1.1.1` patch release from `release-v1.1`.
5. Close the blocker issue.

You have `gh` and `git`.

```bash
gh issue list -R acme/billing
gh repo clone acme/billing
```
