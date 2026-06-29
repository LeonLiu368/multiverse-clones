# Harbor × ghc — local run (validated)

Proof that an agent in a **real Harbor task** can use our `gh` clone (`ghc`) to
operate a Git forge fully offline. The example task lives in
`examples/harbor-ghc-issue/`.

## The task
Instruction: *"using the `gh` CLI, open a new issue titled `GHCTASK-OK` in
`ghc-admin/harbortask`."* The environment image vendors `ghclone`, exposes it as
both `ghc` and `gh`, and points `GHC_HOST` at the host forge
(`host.docker.internal:3300`) with a baked token. The verifier (`tests/test.sh`)
recomputes truth directly from the forge via `gh` — it does not trust agent output.

## Run it
```bash
# forge up + token (see README), then:
export GHC_HOST=http://localhost:3300 GHC_TOKEN=$(cat ghc-token.txt)
export GEMINI_API_KEY=<your key>          # model under test
HARBOR=/path/to/oddish/.venv/bin/harbor   # harbor CLI

# build context needs the ghclone source:
cp -r ghclone examples/harbor-ghc-issue/environment/ghclone

$HARBOR run -p examples/harbor-ghc-issue -a oracle                        # sanity
$HARBOR run -p examples/harbor-ghc-issue -a nop                           # leakage check
$HARBOR run -p examples/harbor-ghc-issue -a terminus-2 -m gemini/gemini-3.5-flash
```
(Reset `ghc-admin/harbortask` between runs for clean gates — `ghc repo delete … --yes` then `ghc repo create harbortask`.)

## Results (2026-06-04, terminus-2 + gemini/gemini-3.5-flash, 3 trials each)
Three sample tasks in `examples/tasks/`, run via the base agent image
(`scripts/build-agent-image.sh`) against the offline forge:

| Task | Exercises | oracle | nop | gemini pass@3 |
|---|---|:--:|:--:|:--:|
| `p0-open-issue` | `gh issue create` | 1 | 0 | **3/3** |
| `p1-triage` | `gh label create` + `issue comment` + `issue close` | 1 | 0 | **3/3** |
| `p0-fix-pr` | `gh repo clone` + git + `gh pr create` | 1 | 0 | **3/3** |

Trajectory excerpt (gemini, p0-fix-pr): clones the repo, `git checkout -b`, edits
`calc.py`, `git push`, then `gh pr create -R ghc-admin/fixme -H fix-div-zero …` —
PR lands with a correct fix. The simpler tasks show *"use `gh auth status` … then
`gh issue create`."*

### Failure analysis (caught + fixed)
`p0-fix-pr` initially scored 0/3. Reading the trajectory showed gemini produced a
**correct** fix and PR, so the fault was the **task**, not the model: the verifier
string-matched and rejected any `return a / b` line — which a correct multi-line
fix keeps for the non-zero branch (the oracle's one-liner slipped past, masking
the bug). Rewrote the verifier to test *behavior* (`div(1,0)==0`, `div(6,2)==3`)
→ 3/3. This is the over-strict-verifier failure mode the eval brief warns about.

## What this validates
- **Harbor runs locally** (image build + agent env + verifier) — the gist's local
  validation loop, done.
- **`ghc` is a drop-in `gh`** inside a task sandbox: the agent discovered auth and
  filed an issue with no code changes, against an **offline Forgejo**.
- nop=0 / oracle=1 gating holds, so the task measures the real capability.

This is the substitute-ghc-for-gh acceptance, now proven with a real model in Harbor.
