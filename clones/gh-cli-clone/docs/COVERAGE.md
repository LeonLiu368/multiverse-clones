# COVERAGE — agent-used `gh` surface → endpoint / CLI / MCP / envelope (Clone Standard R4/R5)

## Real service
- name: GitHub REST API (via the gh CLI)
- api_base: https://api.github.com
- reference: https://docs.github.com/en/rest
- version: 2022-11-28
- snapshot_date: 2026-06-30

Canon coverage matrix for `gh-cli-clone`. One row per capability the agent
realistically needs, each mapped to its **HTTP endpoint** (Forgejo `/api/v1`), its
**CLI** command (`ghc …`), its **MCP** tool (`ghc-mcp`), the **envelope** fidelity
(gh-faithful shape), whether it is **assessment-grade** (AG, see R5), and whether
it is **tested**. The companion `docs/COMMAND-COVERAGE.md` records which agent task
exercises each command; `docs/PARITY.md` is the full gh↔ghc mapping with grades.

Surface size: **41 CLI commands** (9 groups) / **31 MCP tools**, all thin clients
of one `ForgejoClient`. Parity is pinned by `tests/test_parity.py`; envelopes by
`tests/test_client.py` + `tests/test_integration.py`; isolation by
`tests/test_isolation.py`.

Legend — **AG (assessment-grade)** when an endpoint has ≥3 of: stateful round-trip,
multi-step, realistic errors, query/filter grammar, side-effecting devops shape.

| Capability | Endpoint | CLI | MCP | Envelope | AG | Tested |
|---|---|---|---|---|---|---|
| view repo | `GET /repos/{o}/{r}` | `repo view` | `repo_view` | ✅ gh `--json` (`nameWithOwner`,`owner`) | — | ✅ |
| list repos | `GET /user/repos`,`/orgs/{o}/repos` | `repo list` | `repo_list` | ✅ | — | ✅ |
| create repo | `POST /user/repos` | `repo create` | `repo_create` | ✅ prints URL | — | ✅ |
| edit repo | `PATCH /repos/{o}/{r}` (+topics) | `repo edit` | `repo_edit` | ✅ | — | ✅ |
| list issues | `GET /repos/{o}/{r}/issues` | `issue list` | `issue_list` | ✅ `state:"OPEN"/"CLOSED"` | **AG** — filter+state grammar, multi-step list→act | ✅ |
| view issue | `GET …/issues/{n}` | `issue view` | `issue_view` | ✅ | — | ✅ |
| create issue | `POST …/issues` | `issue create` | `issue_create` | ✅ prints URL | **AG** — stateful; observable on later read | ✅ |
| comment issue | `POST …/issues/{n}/comments` | `issue comment` | `issue_comment` | ✅ | — | ✅ |
| close/reopen issue | `PATCH …/issues/{n}` | `issue close`/`reopen` | `issue_set_state` | ✅ `✓ Closed …#n (T)` | **AG** — write→read round-trip | ✅ |
| edit issue (label/ms) | `PATCH …/issues/{n}` | `issue edit` | `issue_edit` | ✅ | — | ✅ |
| react issue | `POST …/issues/{n}/reactions` | `issue react` | `issue_react` | ✅ | — | ✅ |
| list PRs | `GET …/pulls` | `pr list` | `pr_list` | ✅ `state:"MERGED"` | **AG** — filter+state grammar | ✅ |
| view PR | `GET …/pulls/{n}` | `pr view` | `pr_view` | ✅ | — | ✅ |
| create PR | `POST …/pulls` | `pr create` | `pr_create` | ✅ prints URL | **AG** — multi-step (branch→commit→PR) | ✅ |
| diff PR | `GET …/pulls/{n}.diff` | `pr diff` | `pr_diff` | ✅ `diff --git` | — | ✅ |
| review PR | `POST …/pulls/{n}/reviews` | `pr review` | `pr_review` | ✅ `✓ Approved …` | **AG** — side-effecting devops | ✅ |
| merge PR | `POST …/pulls/{n}/merge` | `pr merge` | `pr_merge` | ✅ `✓ Squashed and merged …` | **AG** — write→read round-trip, async mergeability | ✅ |
| close/reopen PR | `PATCH …/pulls/{n}` | `pr close`/`reopen` | (via api) | ✅ | — | ✅ |
| PR checks | `GET …/commits/{ref}/statuses` (overlay) | `pr checks` | `pr_checks` | ✅ gh checks table | — | ✅ |
| list labels | `GET …/labels` | `label list` | `label_list` | ✅ | — | ✅ |
| create label | `POST …/labels` | `label create` | `label_create` | ✅ | — | ✅ |
| delete label | `DELETE …/labels/{id}` | `label delete` | (via api) | ✅ | — | ✅ |
| list milestones | `GET …/milestones` | `milestone list` | `milestone_list` | ✅ | — | ✅ |
| create milestone | `POST …/milestones` | `milestone create` | (via api) | ✅ | — | ✅ |
| close milestone | `PATCH …/milestones/{id}` | `milestone close` | `milestone_close` | ✅ | — | ✅ |
| list workflows | `GET …/actions/workflows` | `workflow list` | `workflow_list` | ✅ | — | ✅ |
| dispatch workflow | `POST …/actions/workflows/{w}/dispatches` | `workflow run` | `workflow_run` | ✅ `✓ Created workflow_dispatch …` | **AG** — side-effecting deploy/dispatch; run executes | ✅ |
| list runs | `GET …/actions/runs` | `run list` | `run_list` | ✅ | — | ✅ |
| view run / logs | `GET …/actions/runs/{id}` (+overlay) | `run view`/`run log` | `run_view`/`run_log` | ✅ | **AG** — investigation: query logs to find a cause | ✅ |
| run artifacts/download | `GET …/actions/runs/{id}/artifacts` | `run artifacts`/`download` | (via api) | ✅ | **AG** — multi-step retrieve build output | ✅ |
| create release | `POST …/releases` | `release create` | `release_create` | ✅ | — | ✅ |
| list releases | `GET …/releases` | `release list` | (via api) | ✅ | — | ✅ |
| raw REST + `--jq` | any `/api/v1/...` | `api` (`-q`) | `api` | ✅ bundled jq engine | **AG** — arbitrary query grammar / escape hatch | ✅ |
| auth status/token | `GET /user` | `auth status`/`token` | (n/a — host config) | ✅ | — | ✅ |

## Assessment-grade set (R5 ≥5; this clone labels **9**)

These carry ≥3 assessment-grade properties and are exercised end-to-end by bundled
tasks:

1. **create issue** → stateful; observable on a later read.
2. **close/reopen issue** → write→read round-trip (the incident task's `incident_closed` gate).
3. **create PR** → multi-step (clone→branch→commit→push→open).
4. **review PR** → side-effecting devops (approve event).
5. **merge PR** → write→read round-trip with async mergeability retry (the `merged` gate).
6. **list issues / list PRs** → filter + state query grammar (`--state all`, label filters).
7. **dispatch workflow** → side-effecting deploy/dispatch; the run actually executes on a host-mode runner.
8. **view run / logs** → read-investigation: query logs to find a failure cause (ci-debug overlay).
9. **raw `api` + `--jq`** → arbitrary query grammar / escape hatch.

The **incident-isolated** task exercises a single end-to-end write→read round-trip
across (1)(3)(4)(5)(2): clone → fix → open PR → approve → squash-merge → close the
incident issue, scored nop=0 / oracle=1. (4)–(8) span read-investigation and
write-action shapes (R5.3).
