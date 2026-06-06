# WORK_LOG — claude-orch-shell

A concise cross-repo status snapshot. Design decisions live in each repo's SPEC; work is
tracked via GitHub Issues and PRs (claude-eng-shell discipline). This file is a quick map,
not a running log.

## The system

| Repo | Tier | Status |
|---|---|---|
| **claude-orch-shell** (this) | coordinator | SPEC done; `routing/` implemented (propose-only `orch evaluate`). |
| **claude-dir-shell** | planning | SPEC done; `lint/` tooling implemented (termination-condition gate + `dir` CLI/workspace). |
| **claude-res-shell** | research | SPEC done; `validation/` tooling implemented (strategic-mode guard). |
| **claude-eng-shell** | execution | **Frozen / external** — consumed only via the Initiative contract; never modified. |

## Load-bearing contracts

- **Initiative (dir→eng)** — code-independent, evaluable termination condition (dir SPEC §3–§4).
- **Research document (caller→res)** — caller-fixed mode; strategic = no code (res SPEC §2–§4).
- **Routing (this repo)** — metadata-only; proposes dir→eng handoffs (SPEC §3–§4).

## Implemented tooling (each offline-tested)

- `routing/` — metadata router + `gh` fetcher + propose-only `orch` CLI.
- `claude-dir-shell/lint/` — termination-condition linter, candidate adapter, filing gate,
  `dir` CLI + workspace scaffolder.
- `claude-res-shell/validation/` — strategic-mode guard + research-document adapter.

## Main remaining pieces

- Shell-invocation **transport** for `orch --auto-invoke` (SPEC §5.2/§9).
- The dir survival/commitment **LLM rubric reviewers** + interactive draft→ground→revise loop.
- The res **request handler** (accept a request, run broad→narrow, emit a document).
- ~~Optional: **submodule promotion** of the three shells under this repo.~~ Done (#29) —
  the three shells are now git submodules (`.gitmodules` + gitlinks); registry shape unchanged.
