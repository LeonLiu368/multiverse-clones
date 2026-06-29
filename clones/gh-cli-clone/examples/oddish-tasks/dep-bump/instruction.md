# Security advisory for `acme/api`

A published advisory, **CVE-2023-32681**, affects `requests` versions **below
2.31.0** — and `acme/api` pins a vulnerable version in `requirements.txt`.

1. Open a pull request that bumps `requests` to a safe version (`>= 2.31.0`).
2. Open a tracking issue that references **CVE-2023-32681** so the team can follow up.

You have `gh` and `git`.
