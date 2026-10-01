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

## Coverage: nine clones
One canonical task per clone, vendored here by `sync_tasks.sh`: notion, figma, google-workspace,
sentry, grafana, logfire, aws, jira and slack. Each is in the **image-pull** shape: `environment/`
holds no clone source. The gateway is pulled (`ghcr.io/abundant-ai/<svc>-service*:...`) and the
agent is `FROM ghcr.io/abundant-ai/<svc>-agent*`.

gh-cli was dropped from the set because its task builds the clone from source instead of pulling
an image, so it isn't self-contained. Its tasks live in `clones/gh-cli-clone/`. discord was added
after this smoke was set up and has its own tasks in `clones/discord-clone/`.

## Running
This is an oddish experiment manifest. Point your oddish/Harbor runner at it
(`task_path: experiments/fleet-smoke/tasks`, `n_trials: 1`). nop and oracle establish the 0/1 floor
and ceiling per task; gemini-cli is the one real-model trial.

> **Images:** most of the `ghcr.io/abundant-ai/...` images these tasks pull are no longer publicly
> pullable. To run a task, build the clone's service and agent images from its folder in `clones/`
> and point the task's `docker-compose.yaml` and `Dockerfile` at your local tags.
