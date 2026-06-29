# gh emulation audit

Goal: an agent cannot distinguish `ghc`'s `gh` from the real GitHub CLI by output
format. Every agent-visible surface is matched to **gh 2.89** — verified against
the installed binary (help/errors) and the `cli/cli` source (success strings).

## Surfaces (all 52 command paths)

| Surface | Status | How verified |
|---|---|---|
| `gh --help`, group `--help`, leaf `--help` | ✅ gh cobra layout | 52/52 render clean (audit harness: zero `[OPTIONS]`/`╭`/`Try '`/`Error:`/completion artifacts; `USAGE` + `LEARN MORE` present) |
| `unknown command "x" for "gh ..."` | ✅ | 10/10 groups, exit 1, stderr |
| `unknown flag: --x` + `Flags:` block | ✅ | 4/4 |
| `accepts 1 arg(s), received 0` | ✅ | 3/3 |
| `gh --version` | ✅ | matches gh's two-line string |
| List output | ✅ TTY `Showing N of M … in O/R` + UPPERCASE cols + relative times (`about N days ago`); piped = gh's exact TSV columns | captured from `gh` binary vs public repos |
| `--jq` / `-q` (on `api` + every `--json` cmd) | ✅ jq expression filter, gh raw output (scalars unquoted, results newline-joined); embedded jq engine bundled in the binary (+jq-binary fallback) | `cli/cli` uses gojq; `ghclone/cli/ghjson.py` |
| `--json <fields>` | ✅ field selection + gh schema (camelCase, top-level sorted, nested struct-order, `state:"OPEN"/"MERGED"`, `/pull/`); empty/invalid → gh's "Specify fields" error | `cli/cli` json_flags + binary; `ghclone/cli/ghjson.py` |
| Detail view (`issue/pr/repo/run view`) | ✅ gh non-TTY `key:\tvalue` + `--` + body | `cli/cli` `view.go` |
| Success messages | ✅ verbatim from source | see below |

## Success-message fidelity (read from `cli/cli` source)

| Command | gh output (matched) | Stream |
|---|---|---|
| `issue/pr/release create`, `issue comment`, `issue edit` | the URL | stdout |
| `repo create` | `✓ Created repository O/R on HOST` + `  URL` | stdout |
| `repo delete` / `repo rename` | `✓ Deleted/Renamed repository O/R` | stdout |
| `repo fork` | `✓ Created fork O/R` | stderr |
| `issue close` / `reopen` | `✓ Closed/Reopened issue O/R#N (Title)` | stderr |
| `pr close` / `reopen` | `✓ Closed/Reopened pull request O/R#N (Title)` | stderr |
| `pr merge` | `✓ {Merged\|Squashed and merged\|Rebased and merged} pull request O/R#N (Title)` | stderr |
| `pr review` | `✓ Approved` / `+ Requested changes to` / `- Reviewed` pull request O/R#N | stderr |
| `label create` / `delete` | `✓ Label "X" created in / deleted from O/R` | stdout |
| `workflow run` | `✓ Created workflow_dispatch event for W at REF` | stderr |
| `run watch` | `✓ Run W (id) completed with 'C'` | stdout |
| `run download` | (silent) | — |
| `auth login` | `✓ Logged in as USER` | stderr |
| `auth status` | gh's multi-line block (host / `✓ Logged in to … account …` / Active account / Git protocol / Token) | stdout |
| `auth logout` | `✓ Logged out of HOST account USER` | stderr |

Icon glyph `✓` and colors (red/magenta/green, `+`/`-` for review) match gh's
`SuccessIconWithColor` usage. API errors print `gh: <message> (HTTP NNN)`.

## Command coverage (every command exercised on oddish)

`cmd-coverage` drives the whole surface in one task; the focused `cmd-*` tasks and
the realistic scenarios cover overlapping subsets.

| Group | Commands | Exercised by |
|---|---|---|
| auth | login¹, status, token, logout¹ | cmd-coverage, every task (healthcheck = `gh auth status`) |
| api | api (+ graphql guard) | cmd-coverage, ci-artifact |
| repo | list, view, create, delete, clone, fork, rename, edit | cmd-coverage |
| issue | list, view, create, comment, close, reopen, edit | cmd-coverage, cmd-issues, triage-sweep, incident-* |
| pr | list, view, create, diff, checkout, merge, close, reopen, review | cmd-coverage, cmd-pr, pr-review, incident-* |
| label | list, create, delete | cmd-coverage, triage-sweep |
| run | list, view, watch, download | cmd-coverage, ci-artifact |
| workflow | list, run | cmd-coverage, cmd-actions, ci-artifact |
| release | create, list | cmd-coverage, release-prep |

¹ `auth login`/`logout` run during environment setup, not by the agent.

Hidden from `--help` (gh has no equivalent; still callable): `milestone` group,
`issue react`, `run artifacts`.

## Known approximations
- **`--json` field coverage**: the common, agent-used fields per resource map to
  gh's schema exactly. GitHub-only fields with no Forgejo equivalent
  (`reactionGroups`, `statusCheckRollup`, `projectCards`, `viewer*`, the opaque
  GraphQL `id`, comment/review arrays) are accepted but return typed empties.
- **Bare `--json`** (no value) hits Click's `Option '--json' requires an argument`
  rather than gh's field list — a Typer optional-value limitation. `--json <bad>`
  *does* give gh's "Unknown JSON field. Available fields:" list.
- **TTY list rendering**: the structure matches (header, columns, relative times),
  but it omits gh's ANSI colors + terminal-width truncation, and shows the page
  count for "of M" (gh shows the true total). Piped TSV is byte-exact.
- **Detail views** use gh's *non-TTY* (`key:\tvalue`) format always; gh renders a
  colorized card to a TTY. The non-TTY form is a real gh mode (deterministic,
  parseable) — chosen over an imperfect card replica.
- **`repo rename`** takes `OWNER/REPO NEW-NAME` (gh infers the repo from cwd/`-R`).
- **Token in `auth status`** is masked (gh shows a `gho_`-prefixed mask; our tokens
  are backend hex, so a fake prefix would contradict `gh auth token`).
- **Frozen binary string** `ghclone.forge` remains in the compiled `gh` (reachable
  only by `grep -a` on the executable; no `strings`/`file` in the container).
