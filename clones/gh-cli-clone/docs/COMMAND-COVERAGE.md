# Command coverage — every ghc command, agent-tested

**Goal: prove an agent can use every command.** Every functional command is exercised
by an agent (gemini-3.5-flash via Harbor, local + oddish). Coverage type:

- ✅ **verifier-required** — an agent task only passes if the agent used this command.
- 🔍 **agent-used** — used to navigate/inform a required step; confirmed by trajectory
  (read-only commands leave no end-state to assert on).
- 🧪 **harness** — `scripts/agent-coverage.sh` (41/41) + live tests. Used for pure
  config/error-path commands with no meaningful agent task.

Agent tasks (all self-contained — forge bundled in-container — run in harbor + oddish):
`incident-fix`, `triage-sweep`, `release-prep`, `dep-bump`, `pr-review`, `ci-artifact`
(realistic scenarios), plus `cmd-issues`/`cmd-pr`/`cmd-actions` (command smoke tests).

## Every command

| Group | Command | Cov | Agent task / note |
|---|---|---|---|
| auth | `status` | 🔍 | every task runs it first |
| auth | `token` | 🧪 | config — harness |
| auth | `login` / `logout` | 🧪 | config — harness (no in-task scenario) |
| repo | `list` | 🔍 | agents browse; harness |
| repo | `view` | 🔍 | incident-fix / cmd-issues |
| repo | `create` | ✅ | cmd-issues (`scratch`) |
| repo | `delete` | ✅ | cmd-issues (asserts `scratch` gone) |
| repo | `clone` | ✅ | incident-fix, dep-bump, pr-review (needed to push) |
| repo | `fork` | ✅ | cmd-pr (asserts `team/svc`) |
| repo | `rename` | ✅ | cmd-issues (asserts `tracker-v2`) |
| repo | `edit` | ✅ | cmd-issues + harness |
| issue | `list` | 🔍 | every issue task |
| issue | `view` | 🔍 | triage-sweep (reads each to decide), incident-fix |
| issue | `create` | ✅ | cmd-issues, dep-bump, ci-artifact |
| issue | `comment` | ✅ | triage-sweep, p1-triage |
| issue | `edit` (+`--add-label`/`--milestone`) | ✅ | triage-sweep, cmd-issues |
| issue | `close` | ✅ | incident-fix, release-prep, triage-sweep |
| issue | `reopen` | ✅ | cmd-issues |
| issue | `react` | ✅ | cmd-issues |
| pr | `list` | 🔍 | cmd-pr, pr-review |
| pr | `view` | 🔍 | incident-fix, pr-review |
| pr | `create` | ✅ | incident-fix, dep-bump, cmd-pr |
| pr | `diff` | 🔍 | pr-review (reviews the change) |
| pr | `checkout` | 🔍 | pr-review (checks the PR out) |
| pr | `merge` | ✅ | incident-fix, cmd-pr |
| pr | `close` | ✅ | pr-review (timeline asserts close→reopen) |
| pr | `reopen` | ✅ | pr-review (asserts reopened) |
| pr | `review` | ✅ | incident-fix, cmd-pr |
| pr | `checks` | ✅ | ci-debug (seeded overlay; exit 1/8) |
| label | `list` | ✅ | cmd-issues (needed to delete by id) |
| label | `create` | ✅ | triage-sweep, p1-triage |
| label | `delete` | ✅ | cmd-issues (asserts gone) |
| milestone | `list` | 🔍 | cmd-issues; harness |
| milestone | `create` | ✅ | triage-sweep, cmd-issues |
| milestone | `close` | ✅ | release-prep (asserts closed) |
| workflow | `list` | ✅ | ci-artifact, cmd-actions |
| workflow | `view` (+`--yaml`) | 🔍 | ci-debug (seeded overlay) |
| workflow | `run` (dispatch) | ✅ | ci-artifact (run actually executes) |
| run | `list` | 🔍 | ci-artifact (waits for the run) |
| run | `view` (+`-v`/`--log`/`--log-failed`/`--job`/`--exit-status`) | 🔍 | ci-debug, ci-artifact; harness |
| run | `watch` | 🔍 | ci-artifact (agent reached for it) |
| run | `artifacts` | ✅ | ci-artifact (downloads the build artifact) |
| run | `download` | ✅ | ci-artifact (deploy code only in the artifact) |
| release | `create` | ✅ | release-prep (asserts release exists) |
| release | `list` | 🔍 | release-prep; harness |
| api | REST / `--paginate` | ✅ | tasks use `gh api …` for checks; harness |
| api | `graphql` (guard) | 🧪 | error-path — harness (errors by design; no GraphQL on Forgejo) |

## Summary
Every **functional** command is agent-tested — verifier-required where it leaves
verifiable state, trajectory-confirmed for read-only ones. The only 🧪-only commands
are `auth token/login/logout` (config) and `api graphql` (an intentional error path):
neither has a meaningful agent scenario, and both are covered by the exhaustive harness.

**Workflows execute for real.** `ci-artifact` runs an in-container host-mode
`act_runner` (no docker-in-docker), so the agent triggers a build, waits for it,
and `gh run download`s the artifact it produced — the full Actions + artifact path.

**Read-only Actions come from a seeded overlay.** For CI-diagnosis tasks (read a
failed run's jobs/steps/logs, inspect a PR's checks) the world ships a per-repo
`actions-seed.json` and `gh run view`/`gh run view --log-failed`/`gh pr checks`/
`gh workflow view` render from it byte-for-byte — deterministic, no act_runner
needed, independent of Forgejo's Actions API gaps. See `docs/ACTIONS-OVERLAY.md`.
