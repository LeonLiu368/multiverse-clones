# Fix a bug and open a PR with `gh`

`gh` is installed and authenticated. The repo **`acme/fixme`** has a bug
(issue #1): `calc.py` defines `div(a, b)` which crashes when `b == 0`.

Do this with `gh` + git:
1. Clone `acme/fixme` (`gh repo clone acme/fixme`).
2. On a new branch, fix `calc.py` so `div(a, 0)` returns `0`.
3. Commit and push the branch.
4. Open a pull request into `main` (`gh pr create`).
