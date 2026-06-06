# Creating a new task

These are **observability + codebase** tasks: a failing test suite at `/workspace` whose fix
depends on a fact that lives **only** in heavy, noisy Slack history. The full authoring
checklist (with the anti-reward-hacking rules and the pytest-collection gotcha) is encoded in
the **`slack-observability-task-builder`** skill — invoke it when building one. This page is the
quick version.

## What types of tasks fit
Anything where the *fix-critical* information can be buried in chat and is hard to recover, e.g.:
- **buried-spec** — implement a function whose policy was agreed in chat (superseded proposals).
- **contract-drift** — update client code to an API change announced in chat (mid-thread correction).
- **incident-fix-report** — diagnose a bug from an incident thread, fix it, **and** post a
  postmortem (action beyond coding).
Other ideas: a magic constant/threshold decided in chat; a config value; a data-format detail in
pasted logs; "who owns X / what was decided" that gates the change.

## The two bars (non-negotiable)
1. **Tool use is CRITICAL** — the fact is only in chat; a hidden grader (parameters only in chat)
   makes the answer unobtainable from the repo or visible tests.
2. **Tool use is NON-TRIVIAL** — superseded/contradictory values, a decision spread across a
   thread, off-channel traps, a red herring. `search.messages` should surface the *wrong* hits
   too, so the agent must read and disambiguate.

## Anatomy (copy an existing task — e.g. `buried-spec`)
```
tasks/<name>/
  task.toml            # service="slack", tools=["slack"], workdir="/workspace", mcp_servers=[slack]
  instruction.md       # the symptom + "use the slack tool"; NEVER the buried fact
  environment/
    Dockerfile, slack, slack-mcp.sh, client-entrypoint.sh    # the client + slack facade (copy)
    mattermost/{Dockerfile,entrypoint.sh,seed.py}            # chat backend + seeder (copy)
    data/mattermost/{generate.py, scraped.json}  ← YOU WRITE generate.py, commit scraped.json
    codebase/          ← YOU WRITE: working module(s) [tests pass] + a stub/buggy target [fails],
                         with a breadcrumb (docstring/README/error) pointing to chat
  solution/solve.sh    ← YOU WRITE: oracle (edits only /workspace; for incident-style, also posts)
  tests/
    test.sh                                  # orchestration (copy)
    run_verifier.sh    ← YOU WRITE/ADAPT: grade in /tmp; reward by pytest exit (+ any comms check)
    trusted/           ← YOU WRITE: canonical visible tests + the HIDDEN test_grade_*.py
```
To create one, copy `buried-spec`, then swap: `codebase/`, `data/mattermost/generate.py` (+regen
`scraped.json`), `tests/trusted/*`, `solution/solve.sh`, `instruction.md`, `task.toml`, and the
`package`/`grade` names in `run_verifier.sh`. Give the client image a unique default tag in
`docker-compose.yaml` (e.g. `${...:-<name>-client:local}`) to avoid local cross-task collisions.

## Rules that keep it reliable (from hard-won experience)
- **Visible tests are invariant-only** — never encode the buried parameters.
- **Hidden grader MUST be named `test_grade_*.py`** — pytest only auto-collects `test_*.py`; a
  `grade_*.py` silently won't run and grading degrades to the invariants (a false-pass hole).
- **Grade in a fresh verifier-owned dir** (`/tmp/grade.$$`): copy the candidate package + trusted
  tests there and run pytest there — never run `/workspace/tests`. Defeats test tampering.
- **Seed via REST, mutate via REST** (the shared `seed.py` creates users/channels via REST,
  posts via SQL for timestamps). Raw-SQL entities don't behave under app ops.
- **Key reward on the fixed state.** Confirm a *deliberately wrong* impl that satisfies the
  invariants still scores 0 (proves the grader runs and bites).

## Validate before shipping (always)
```bash
cd tasks/<name>/environment && docker compose up -d --build
docker cp ../tests client:/tests && docker cp ../solution client:/solution
docker compose exec -T client bash /tests/run_verifier.sh                      # nop -> 0
# wrong-but-invariant impl -> must still be 0  (write it, re-run)
docker compose exec -T client bash /solution/solve.sh
docker compose exec -T client bash /tests/run_verifier.sh                      # oracle -> 1
docker compose down -v
```
Also: `task.toml` validates against Harbor's `TaskConfig`/`MCPServerConfig`; compose has no
explicit `networks:`; both services pin `platform: linux/amd64`. For deeper QA run the
`skillz:harbor-task-audit` and `verifier-attack-lab` skills.
