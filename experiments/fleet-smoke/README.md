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
| grafana-annotation-roundtrip | grafana-clone | write→read: find firing alert → post annotation |
| logfire-incident-rca | abundant-logfire-clone | read: SQL RCA → fix |
| aws-payment-reconcile | aws-clone | write→read: reconcile payment via SQS/S3/DynamoDB |

### The other 3 clones (gh-cli, jira, slack): join via PULL once images are published
These three tasks aren't self-contained the way the 7 above are — their gateway `build:` context is the
clone's **shared** `selfcontained/`/`docker/` dir (relative path outside the task), and their agents
pull CLI binaries from images. So rather than vendoring build contexts, they fold into the smoke by
**pulling the published owner images** once the CI has run:

1. Run `mirror-upstream-bases.yml` (mirrors the private `ticketvector-service` + `slack-seed` bases
   into `ghcr.io/leonliu368`, read-only — never touches abundant-ai).
2. Run `publish-images.yml` (gh-cli image) + `publish-jira-slack.yml` (jira/slack images) → all gateway
   images live public under `ghcr.io/leonliu368`.
3. Add their tasks here with the gateway pinned to the published image, e.g.
   `image: ghcr.io/leonliu368/jira-gateway:prod-v1` (pull, no `build:`), and the agent built from the
   clone's vendored tools. (gh-cli also needs `scripts/vendor-tasks.sh` run to vendor `ghclone`.)

Keeping them pull-based keeps the smoke self-hosted in your registry and avoids re-vendoring shared
build contexts. They're left out of v1 only because that repoint can't be validated until the images
are actually published.

## Running
This is an oddish experiment manifest. Point your oddish/Harbor runner at it
(`task_path: experiments/fleet-smoke/tasks`, `n_trials: 1`). nop and oracle establish the 0/1 floor and
ceiling per task; gemini-cli is the one real-model trial. Tasks build their gateway locally via the
`build:`+`image:` dual, so no registry pull is required — but once `publish-images.yml` has published
the trios to `ghcr.io/leonliu368/<svc>-service:prod-v1`, the tasks can be repointed to pull instead.
