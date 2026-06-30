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

## Coverage (v1: 7 of 10 clones)

| Task | Clone | Shape |
|---|---|---|
| notion-db-triage | notion-clone | write→read: query DB → update status → comment |
| figma-spec-recovery | figma-clone | read: recover design spec → apply to code |
| gws-launch-date-prod-v1 | google-workspace-clone | read: recover a launch date from Drive/Docs |
| sentry-payments-incident | sentry-clone | write→read: triage → resolve + comment |
| gauge-annotation-roundtrip | gauge | write→read: find firing alert → post annotation |
| logfire-incident-rca | abundant-logfire-clone | read: SQL RCA → fix |
| aws-payment-reconcile | aws-clone | write→read: reconcile payment via SQS/S3/DynamoDB |

### Deferred (re-add as they're unblocked)
- **gh-cli-clone** — its runnable 2-container task (`examples/oddish-tasks/incident-isolated`) needs
  `ghclone` vendored into `environment/` before `compose build` (an undocumented prereq); fold it in
  once that's scripted.
- **abundant-jira-clone**, **abundant-slack-clone** — their gateway `:prod-v1` builds **FROM a private
  abundant-ai base image** (`ticketvector-service` / `slack-seed`). They'll run here once those bases
  are mirrored to the owner's registry (the same blocker called out in `publish-images.yml`).

## Running
This is an oddish experiment manifest. Point your oddish/Harbor runner at it
(`task_path: experiments/fleet-smoke/tasks`, `n_trials: 1`). nop and oracle establish the 0/1 floor and
ceiling per task; gemini-cli is the one real-model trial. Tasks build their gateway locally via the
`build:`+`image:` dual, so no registry pull is required — but once `publish-images.yml` has published
the trios to `ghcr.io/leonliu368/<svc>-service:prod-v1`, the tasks can be repointed to pull instead.
