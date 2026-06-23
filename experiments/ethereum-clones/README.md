# ethereum-clones

APEX-SWE-style **Ethereum (Optimism `op-geth`)** observability/devops incident task(s)
re-platformed onto abundant-ai's service clones — discover a production issue through the
local **ticketvector** (`linear`/`jira`) tracker, fix the root cause in `/app/repo`, and close
the ticket with evidence. The upstream `op-geth` repo, the planted bug, `golden.patch`,
`test.patch`, and the hidden Go test are preserved verbatim; only the diagnostic substrate is a
clone (the upstream ticketvector service). Grading is clone-independent code grading
(`go test ./params`) **plus** a ticket-workflow-evidence check.

## Tasks

| Task | Repo / PR | F2P (hidden test) | Status |
|---|---|---|---|
| `op-geth-770` | `ethereum-optimism/op-geth` #770 | `go test ./params` → `TestIsOptimismGenesisBlock` | **shipped** |

### op-geth-770 — OP genesis extraData validation

The Jovian/Optimism `extraData` validation rejected the OP-Mainnet genesis block (which carries
non-empty extraData). The fix adds `ChainConfig.IsOptimismGenesisBlock` and skips extraData
validation for the genesis block only, leaving every other block's checks intact
(`consensus/beacon`, `consensus/misc/eip1559`, `params/config.go`). The hidden regression test
`TestIsOptimismGenesisBlock` is a pure table-driven config test → **deterministic** (the
class the apex-swe-clones determinism triage prefers; see that README).

Source: ported from the `variant-ethereum-optimism-op-geth-770-observability` task on
`josh/apex-swe-devops-batch2` (vendored `op-geth` snapshot + `world_issues` ticketvector runtime
+ `golden.patch`/`test.patch`/`ticketvector-state.json`), self-contained — no GHCR pull or HF
fetch needed at build.

**Local gate (native arch, `golang:1.24`, `go test ./params -run TestIsOptimismGenesisBlock`):**
- oracle (golden+test) → **PASS ×3** (deterministic, all 9 subtests).
- nop (test only) → **FAIL** (build error: `OPMainnetGenesisBlockNum` / `IsOptimismGenesisBlock`
  undefined). nop=0, oracle=1 at the code-grading layer.

The full verifier (`tests/test.sh`) additionally runs `check_ticket_state.py`: the primary
ticket `TV-770` must be moved to **In Review** through the tracker by `agent`, with an
investigation comment, a `commit:` link, a PR receipt, and **no** mutation of the distractor
tickets. The oracle `solution/solve.sh` drives the `linear`/`jira` CLIs to satisfy this; nop
does neither. Validated end-to-end by the Oddish run (see `ethereum-clones-manifest.yaml`).

## Attempted but blocked (source unavailable)

The other ethereum `op-geth` tasks were attempted and could not be shipped — recorded here so we
don't re-derive the same dead ends:

- **`op-geth-703`** — the task named by the `task-files-variant-ethereum-optimism-op-geth-703-observability`
  git tag. **No source exists anywhere**: no committed task files in any git ref (only the
  `-770` variant was ever extracted, on `josh/apex-swe-devops-batch2`), and `mercor/APEX-SWE`'s
  `Observability/` set currently contains only `0xpolygon-bor-{1710,1728-1748,1743}` — no
  `ethereum-optimism` task at all. Nothing to convert.
- **`op-geth-655`** — the *exact* `Observability/ethereum-optimism-op-geth-655-observability`
  APEX task (previously converted onto the clone stack in `apex-swe-clones`, then **dropped as
  flaky**: its F2P is the whole `./miner` package — `TestDAFilters`/`TestBuildPayload`, async
  payload-building with `t.Parallel()` + exact tx-count asserts — which passes unloaded but fails
  under load on Oddish amd64). It is also now **un-buildable**: its `Dockerfile` fetches
  `Observability/ethereum-optimism-op-geth-655-observability/repo/**` from `mercor/APEX-SWE`,
  a path the dataset no longer contains.

To revive either, we need their source restored (the op-geth tasks re-added to `mercor/APEX-SWE`,
or a fresh variant extraction) — at which point op-geth-703 would convert exactly like op-geth-770,
and op-geth-655 would still need a deterministic F2P (not `./miner`).
