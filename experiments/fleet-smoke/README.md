# fleet-smoke

A simple **fleet smoke**: one bundled read/write task per clone, run with **nop + oracle + gemini ×1**.
The point is a single, cheap signal that the whole fleet is runnable end-to-end and that a real model
(gemini) can operate each clone through its CLI/MCP — not a full benchmark.

## What's here
- `fleet-smoke-manifest.yaml` — the oddish experiment (agents = nop, oracle, gemini-cli; `n_trials: 1`).
- `tasks/<name>/` — each clone's bundled task, vendored self-contained (agent+gateway, `build:`+`image:`
  dual, no `networks:`). Every one is deterministic **nop=0 / oracle=1** and was audited to meet
  Clone Standard v1.
- `sync_tasks.sh` — regenerates `tasks/` from the in-repo clone tasks (`clones/<clone>/.../<task>`).

## Coverage — all 10 clones
Every clone's canonical task is vendored here (via `sync_tasks.sh`), each in the **image-pull** shape:
`environment/` has no clone source — the gateway is pulled (`ghcr.io/abundant-ai/<svc>-service*:...`)
and the agent is `FROM ghcr.io/abundant-ai/<svc>-agent*`. notion, figma, google-workspace, sentry,
grafana, logfire, aws, jira, slack, gh-cli.

> **Runner access:** the published packages are currently **private**. To run this smoke on Oddish (or
> any external runner), flip the `<svc>-service*` / `<svc>-agent*` packages to **internal/public** in
> GitHub → abundant-ai → Packages (container-package visibility is UI-only; there's no API for it).

## Running
This is an oddish experiment manifest. Point your oddish/Harbor runner at it
(`task_path: experiments/fleet-smoke/tasks`, `n_trials: 1`). nop and oracle establish the 0/1 floor and
ceiling per task; gemini-cli is the one real-model trial. Tasks build their gateway locally via the
`build:`+`image:` dual, so no registry pull is required — but once `publish-images.yml` has published
the trios to `ghcr.io/leonliu368/<svc>-service:prod-v1`, the tasks can be repointed to pull instead.
