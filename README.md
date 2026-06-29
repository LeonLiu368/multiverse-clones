# multiverse-clones

Monorepo for the **clones** — the containerized stand-ins for real SaaS APIs that
[`abundant-ai`](https://github.com/abundant-ai) agent-eval tasks (Harbor / Oddish) run
against. This repo is where we **create, verify, and scale** clones in one place.

## Layout

```
clones/            Vendored full source of every abundant-ai service clone, plus the
                   Dockerfiles and docker-compose setups a task needs to stand each one up.
                   See clones/README.md for the inventory and clones/MANIFEST.json for
                   upstream provenance (repo + commit each folder was vendored from).
```

More to come (verification harness, scaling tooling) — added as we go.

## Vendoring

Clones are stored as **full source copies**, not submodules: each `clones/<name>/` is the
upstream `main` tree with its `.git` removed. `clones/MANIFEST.json` pins the exact commit
each was taken from so any clone can be re-synced from upstream on demand.
