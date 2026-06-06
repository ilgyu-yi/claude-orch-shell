# claude-orch-shell

**claude-orch-shell** coordinates a three-shell Claude Code system — planning, execution,
and research — to produce exceptional output.

```
        MISSION (stated direction)
            │
   ┌────────▼─────────┐   Initiative (dir→eng contract)   ┌──────────────────┐
   │   claude-dir-shell│ ───────────────────────────────► │  claude-eng-shell │
   │   (planning tier) │                                  │  (execution tier) │  [FROZEN]
   │  produces         │                                  │  consumes         │
   │  Initiatives      │                                  │  Initiatives →    │
   └───────┬───────────┘                                  │  Directives → ... │
           │  research request (strategic)                └────────┬──────────┘
           ▼                                                        ▼  research request (technical)
   ┌────────────────────────────── claude-res-shell ──────────────────────────────┐
   │  on-demand research subroutine — returns a document used as evidence;          │
   │  called by dir (strategic, no code) or eng (technical, code-ok); makes no      │
   │  decisions; no outgoing edges                                                  │
   └───────────────────────────────────────────────────────────────────────────────┘

   claude-orch-shell (this repo) is type-A "plumbing": it reads METADATA only, proposes
   stage handoffs (dir→eng via the Initiative), and never interprets content or makes
   strategic/execution judgments. It does not see res calls (they are stage-internal).
```

## Components

| Component | Repo | Tier | Role |
|---|---|---|---|
| **claude-orch-shell** | this repo (top level) | — | Metadata-only router; proposes dir→eng handoffs. [SPEC.md](SPEC.md) |
| **dir-shell** | `claude-dir-shell/` | planning | Produces Initiatives carrying a **code-independent evaluable termination condition**. [SPEC](claude-dir-shell/SPEC.md) |
| **eng-shell** | `claude-eng-shell/` | execution | Consumes Initiatives → Directives → execution. **Frozen / out of scope** — never modified here. |
| **res-shell** | `claude-res-shell/` | research | On-demand research subroutine; returns a document as evidence; caller-fixed mode (strategic/technical). [SPEC](claude-res-shell/SPEC.md) |

## The load-bearing contracts

- **Initiative (dir→eng)** — every filed Initiative carries a termination condition that is
  **decidable, code-independent, attributable, bounded**: *what done means*, evaluable
  without reading code. dir guarantees it at a non-skippable gate. dir SPEC §3–§4.
- **Research document (caller→res)** — res's **mode** is fixed by the caller: a `dir` call
  is strategic (no code, ever); an `eng` call may be technical. One invocation, one mode,
  never mixed. res SPEC §2–§4.
- **Routing (claude-orch-shell)** — claude-orch-shell routes on metadata only (`initiative` label
  + Active state + `Parent Initiative: #N` marker presence), proposes handoffs, and trusts
  the stages' gates. SPEC §3–§4.

## Repository layout & git

This top-level repo is itself a git repo with its own GitHub remote. The three shells are
**independent git repos** nested as **git submodules** (`.gitmodules`), so claude-orch-shell
tracks only a pinned gitlink per shell and never absorbs their contents. Commit changes to
each shell **inside that shell** (then bump the gitlink here); commit claude-orch-shell's own
files here. Clone with `git clone --recurse-submodules`, or run `git submodule update --init`
in an existing checkout. Each repo follows the same flow (below).

## Process

Engineering follows **claude-eng-shell discipline**: Issue → branch → PR (`Closes #N`) →
merge (no-ff); conventional commits `type(#issue): subject`; Doc→Test→Code phasing for
features; `changelog_unreleased/<category>/<PR>.md` fragments consolidated into
`CHANGELOG.md` + `VERSION` at release. **SPECs are the source of truth for design** —
spec-first: no implementation of a unit until its SPEC section is complete.
[WORK_LOG.md](WORK_LOG.md) holds a concise cross-repo status snapshot.

## Status

All three SPECs are authored and internally consistent. The `routing/` tooling is
implemented — the propose-only `orch evaluate` CLI over a metadata-only router. The
shell-invocation transport (for `--auto-invoke`) is the main remaining piece (SPEC §5.2/§9).
