# How agents try to tell they're in a simulation

*Case study: an offline GitHub CLI (`gh`) backed by Forgejo, run in sandboxed
"worlds." We watched real agent trajectories (gemini via terminus-2, on oddish)
probe the environment. These are **observed agent behaviors**, quoted verbatim.*

> oddish has no per-trajectory URL — open the experiment link, then click the
> named trial to see the episode.

---

## 1. Host fingerprinting from conventions

The agent couldn't read any backend name, so it inferred from URL/port conventions
— and could never pin it down.

- **[90910e4b](https://www.oddish.app/share/im55qyNINv4f8xwFfr5rCi7mOl1-bGRoGczRRyTNXcM)** · `incident-isolated-f592134a-3` · ep-15:
  > *"…we are doing this in a test environment (**Gitea/Forgejo on http://10.88.0.2:3000**)…"* — triggered by the `:3000` port (Gitea's default).
- **[a93c3e97](https://www.oddish.app/share/GWMGqWjBqhtBYJ6cHtrditXMm4nmnP573-JWMFlfoNg)** · `pr-review-f0cce8ce-3` · ep-2:
  > *"…a **GitHub-compatible service (like Gitea or GitHub Enterprise)** hosted at http://10.88.0.2."*
- After moving the backend to port 80 + a neutral IP — **[a8997b48](https://www.oddish.app/share/3tcTNT9PZhu_K60pkRO5RosTQvMR1NSsig8x8v4GNBU)** · `release-prep-6d197b09-5` · ep-1:
  > *"We are authenticated to a **self-hosted GitHub/Gitea/Gitlab-like instance** at 10.88.0.2 using account `acme`."* — still can't pin it; lists three candidates and moves on.

## 2. Tooling-format fingerprinting (the surprising one)

The agent fingerprinted the **CLI itself**, not the backend — purely from output
*style*.

- **[a93c3e97](https://www.oddish.app/share/GWMGqWjBqhtBYJ6cHtrditXMm4nmnP573-JWMFlfoNg)** · `cmd-pr-685816fe-2` · ep-10:
  > *"the `gh` version is different (maybe a **custom wrapper, or a python-based CLI** since the errors are styled with **`rich` style error boxes**, e.g. `Usage: gh auth [OPTIONS] COMMAND [ARGS]...`)."*

  Our `rich`-bordered `╭─ Error ─╮` panels + Typer usage strings gave it away as
  not the real Go/cobra `gh`. We then reproduced gh's help/error/table output
  byte-for-byte. In the latest run (**a8997b48**, 8 trajectories) **no agent
  flagged the CLI** — the tell is gone.

## 3. Process / network recon

- **Single-container (the motivating case, earlier run):** an agent ran recon and
  reported *"Forgejo is running as a local git server on port 3000"* — the forge
  process and port were in the agent's own namespace. This drove the switch to a
  multi-container layout.
- **Multi-container (verified — [a8997b48](https://www.oddish.app/share/3tcTNT9PZhu_K60pkRO5RosTQvMR1NSsig8x8v4GNBU) · `incident-fix-c81dc0c1-10`):** an agent ran the *same* playbook — and the forge was gone:
  ```
  $ ps aux      → bash: ps: command not found
  $ ss -tulpn   → bash: ss: command not found
  $ env         → GH_HOST=http://10.88.0.2   (just the IP)
  ```
  `ps`/`ss` aren't installed, and the forge lives in a separate namespace anyway —
  no process, no port. The recon surfaced exactly one thing (see #4) and the agent
  returned to the task without a conclusion.

## 4. Orchestration-artifact discovery

The *one* thing the multi-container recon found was the plumbing itself. Same
trajectory (**[a8997b48](https://www.oddish.app/share/3tcTNT9PZhu_K60pkRO5RosTQvMR1NSsig8x8v4GNBU)** · `incident-fix-c81dc0c1-10`):
```
$ ls -la /shared /root
/shared:
  ready    (6 bytes)
  token    (41 bytes)
```
The agent had stumbled onto the **shared volume** the two containers use to pass
the token — and a gratuitous `ready` marker (our internal "forge is up" signal).
It **drew no conclusion** and moved on, but a token sitting in a dir literally
named `/shared`, next to a `ready` file, is an "someone *orchestrated* this" tell.

**Fix (verified — [2d5e5a9a](https://www.oddish.app/share/b8ewTXFesl0T9Y3DupuuwCTx0kDqP_PP9tc5q4JtmS0)):** make
the delivery look native. The token now arrives at `/run/secrets/` (the standard
secrets path), `gh`'s real config dir `~/.config/gh/hosts.json` is seeded so it
looks logged-in, and the `ready` marker stays on the backend's own filesystem.
Post-fix, `/shared` does not exist anywhere in the agent's container — recon finds
a normal-looking gh setup and nothing else.

---

## The irreducible floor

A private host speaking GitHub's API is **genuinely indistinguishable from GitHub
Enterprise**. Agents correctly land on *"self-hosted, maybe GHE/Gitea/GitLab"* and
stop. You can hide the *identity*; you can't hide the *category*.

## Takeaways

- Agents reach for *"is this a wrapper / a sim?"* remarkably early — often from
  output **style and conventions** (port numbers, URL paths, CLI error rendering),
  not from behavior.
- Isolation is **layered**, and each layer is a distinct surface: namespace
  (process/port), naming (URLs/secrets), statistical (ports/paths), tooling-format
  (how your tools *render*), and **orchestration artifacts** (shared volumes,
  readiness markers, mount paths — the scaffolding leaking into view).
- The tooling-format tell is the easy one to miss: a faithful wrapper still gives
  itself away if its output doesn't match the real tool byte-for-byte.
- Your own plumbing is a tell. Once the obvious leaks are closed, the remaining
  signal is the *infrastructure* — name your mounts/paths like a real environment
  would (`/run/secrets`, `~/.config/gh`), and keep internal markers off any
  surface the agent shares.

*Honesty note: all quotes above are observed in trajectories. The single-container
"found Forgejo" quote is from an earlier run surfaced during the investigation and
not personally re-pulled; everything with an experiment link is verified.*
