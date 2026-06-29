# Fix a bug and open a PR with `gh`

`gh` is installed and authenticated. The repo **`ghc-admin/fixme`** has a bug
reported in **issue #1**: `calc.py` defines `div(a, b)` which crashes on `b == 0`.

Do this:
1. Clone `ghc-admin/fixme` (`gh repo clone ghc-admin/fixme`).
2. On a new branch, fix `calc.py` so `div(a, 0)` returns `0` instead of crashing.
3. Commit and push the branch.
4. Open a **pull request** into `main` with your fix (`gh pr create`).
