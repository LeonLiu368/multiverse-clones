# Clone seed schemas (conversion targets)

Authoritative shapes the three clone images load. Sources verified against the live
clone repos and a committed working task-pack.

## ticketvector  (Plane stand-in)
- Sidecar `ghcr.io/abundant-ai/ticketvector-service:main`, `network_mode: service:main`,
  reads `WORLD_ISSUES_STATE_FILE=/var/lib/ticketvector/state.json` (JSON, loaded directly).
- Agent tools (copied into `main`): `/usr/local/bin/{linear,jira}` + `/opt/ticketvector`.
- `state.json` keys: `workspace`, `base_url`, `project{id,key,name,archived}`,
  `users[{id,handle,name}]`, `states[{id,name,category}]`, `labels[{id,name}]`,
  `modules[]`, `cycles[]`, `relations{}`, `links{}`, `history[]`, `attachments{}`,
  `issues[{id,identifier,title,description,state{id,name},assignees[{id,handle,name}],
  labels[{id,name}],priority,created_at,updated_at,comments_count}]`,
  `comments{ "<identifier>": [{id,author{id,handle,name},body,created_at}] }`.
- State categories: unstarted | started | completed | cancelled. `linear issue mine`
  surfaces issues assigned to handle `agent`.

## slack-service  (Mattermost stand-in)
- Sidecar `ghcr.io/abundant-ai/slack-service:latest`, EXPOSE 80, mount
  `./data/slack:/data/mattermost:ro` (seeded by the image's own task-seed.sh + seed.py).
  `main` talks to it via `SLACK_API_URL=http://slack`.
- Agent tools (copied into `main`): `/usr/local/bin/{slack,slack-mcp}` + `/opt/slackcli`
  (PYTHONPATH `/opt:/opt/slackcli`).
- `scraped.json`: `{ "messages": [ {channel, author, content, timestamp} ] }`.
  IMPORTANT: `author` is a plain string (username), not an object.

## gauge  (Grafana + Loki + Prometheus stand-in)
- Sidecar `ghcr.io/abundant-ai/gauge-service:main`, EXPOSE 80, `/api/healthz`,
  reads `GAUGE_STATE_FILE=/data/gauge/state.json` (ro), mutates
  `GAUGE_RUNTIME_STATE_FILE=/var/lib/gauge/state.json`. `main` reaches it at
  `GRAFANA_URL=http://gauge`.
- Agent tools (copied into `main`): `/usr/local/bin/{gcx,mcp-grafana}` + `/opt/gaugecli`.
  (`gaugectl` is admin-only — do NOT copy into `main`.)
- `state.json` keys: `meta{workspace,now}`, `users[]`, `datasources[{uid,name,type,
  mode:"embedded",health:"ok"}]`, `dashboards[{uid,title,folder,tags,variables,panels}]`,
  `alerts[]`, `metrics{queries:{"<promql>":{resultType,series[{metric,values[[ts,val]]}]}}}`,
  `logs{queries:{"<logql>":{entries:[{ts,labels,line}]}}}`,
  `alert_instances[]`, `alert_state_history[]`, `annotations[]`, `mutation_log[]`.
- Log queries: gauge has a real (simple) LogQL engine. Exact fixture-key match wins;
  otherwise it filters ALL loaded entries by selector `{k="v",...}` + optional
  `|= "substring"`. So loading every log line as an `entries[]` item (with correct
  `labels`) makes it retrievable by any plausible selector. Selector keys are a subset
  check, so extra entry labels are harmless.

## What is NOT converted (pass-through, copied verbatim)
`repo/` (or build-time clone @ base_commit), `solution/golden.patch`,
`tests/test.patch`, `tests/test_metadata.json` (F2P/P2P), `instruction.md`.
Grading runs pytest on `/app/repo` after applying `test.patch` — fully independent
of the clones (clones are the diagnostic surface only).
