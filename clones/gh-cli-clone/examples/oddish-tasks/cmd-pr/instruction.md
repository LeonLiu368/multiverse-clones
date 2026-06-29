# Ship a fix via a pull request with `gh`

`gh` is installed and authenticated. The repo **`acme/svc`** has a bug
(issue #1): `calc.py` `div(a, b)` crashes when `b == 0`. An organization named
`team` exists. Using `gh` + git, do **all** of:

1. Fork `acme/svc` into the `team` organization.
2. Clone `acme/svc`, create a branch, fix `calc.py` so `div(a, 0)` returns `0`, commit, and push.
3. Open a pull request into `main`.
4. Approve the pull request (`gh pr review --approve`).
5. Merge the pull request.
6. Close issue #1.
