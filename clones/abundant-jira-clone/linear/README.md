# linear/ — Linear-faithful GraphQL surface

The jira-gateway serves Plane-REST + a `linear` CLI skin; a real Linear GraphQL client or
**linear-mcp** (which POSTs to `api.linear.app/graphql`) can't talk to it. `linear/server.py`
serves the same GraphQL shape over the SAME `state.json` the gateway bakes — run it as a
**sidecar** next to jira-gateway so an agent's real Linear tooling works.

- `tools/linear_to_state.py` — captures a real Linear workspace (GraphQL) → `state.json`.
- `linear/server.py` — `POST /graphql` (viewer/organization/teams/users/workflowStates/issues
  (+filter)/issue/comments), read-only, `Authorization` checked vs `LINEAR_TOKEN`.
- `linear/build.sh <state.json> <tag>` — bake a corpus into a `linear-gateway` image (:80).
