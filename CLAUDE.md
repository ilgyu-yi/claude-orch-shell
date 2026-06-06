# claude-orch-shell — Operating Norms

Operating manual for this repo, read by Claude Code at session start. Authoritative design:
[SPEC.md](SPEC.md). Direction: [MISSION.md](MISSION.md).

## Status

**[SPEC.md](SPEC.md) is the source of truth** for design. The `routing/` tooling is
implemented (propose-only `orch evaluate`); the shell-invocation transport is the main
remaining piece (SPEC §5.2/§9). Spec-first: don't implement a unit until its SPEC section is
complete; if implementation reveals the spec is wrong, fix the spec first.

## Core norms

### 1. Type-A plumbing — metadata only
claude-orch-shell reads **metadata only** (labels, issue state, close reason, marker/section
presence) and **never** artifact content (no prose, no termination-condition text, no code).
It **proposes** stage handoffs and makes **no** strategic/execution judgment — stages own
their gates (SPEC §1, §4). The routing core takes a body-less struct so content reads are
structurally impossible.

### 2. res is invisible; eng is frozen
Research calls are stage-internal subroutines of dir/eng — claude-orch-shell neither sees nor
routes them (SPEC §6). **claude-eng-shell is a frozen external system** — never written to;
consumed only via the Initiative contract.

### 3. The repository layout
The three shells are independent git repos nested here as **git submodules** (`.gitmodules`);
orch tracks only a pinned gitlink per shell, never their contents. Commit each shell's changes
**inside that shell**, then bump the gitlink here; commit claude-orch-shell's own files here.

## Engineering discipline (adopted from claude-eng-shell)

- **Issue → branch → PR → merge.** File a typed Issue; branch
  `<gh-username>/<type>/<issue#>-<slug>`; PR ends with `Closes #<N>` (or `Refs #<N>`); merge
  into `main` with a **merge commit** (no squash/rebase on the default branch).
- **Conventional commits.** `<type>(#<issue>)[!]: <subject>` (≤ 72 codepoints). Types
  `feat fix docs refactor perf` (issue # required) · `test style build ci chore revert`
  (issue # optional). Optional `Co-Authored-By: Claude <noreply@anthropic.com>`.
- **Doc → Test → Code** phased commits for features; relaxed for fix/refactor/perf.
- **Changelog fragments.** Each PR with an observable change adds
  `changelog_unreleased/<category>/<PR>.md` (`- … (#<PR>)`); internal-only PRs use the
  `skip-changelog` label. Releases consolidate fragments into `CHANGELOG.md` + bump `VERSION`.

## Boundary

- Never modifies user-global state (`~/.zshrc`, global git config, `~/.claude/` outside the
  auto-memory tier).
- Never writes to claude-eng-shell.
