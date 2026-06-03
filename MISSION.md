# MISSION — claude-orch-shell

claude-orch-shell is the **coordinator** of a three-shell Claude Code system —
claude-dir-shell (planning), claude-eng-shell (execution), claude-res-shell (research). Its
job is to move artifacts between stages so the combined system produces exceptional output.

## The load-bearing idea

claude-orch-shell is **type-A plumbing, not a commander**. It reads **metadata only** (labels,
issue state, marker/section presence) — never artifact content — and **proposes** stage
handoffs (today: dir→eng via the Initiative). It makes no strategic or execution judgment;
it trusts each stage's own gates. Research calls are stage-internal and invisible to it. See
[SPEC.md](SPEC.md) §1–§4.

## Shared principle — context narrowing

All four shells of this system — claude-orch-shell, claude-dir-shell, claude-eng-shell,
claude-res-shell — share one load-bearing principle, articulated first in
[claude-eng-shell's MISSION](https://github.com/ilgyu-yi/claude-eng-shell/blob/main/MISSION.md)
("The mechanism"): **an AI agent's output quality is bounded by the size and relevance of its
working context.** So every design choice keeps the slice of context the model reasons over
**as small and relevant as possible** — pushing irrelevant material *out* (narrowing) and
pulling relevant material *in* from durable memory on demand (selective injection). The two
are dual: narrowing alone starves (hallucination from absence); injection alone distracts.
**Artifacts — not long-running conversations — are the boundaries and the durable memory**;
each tier is a context boundary whose output is the next tier's input.

**This is the evaluation criterion.** Every proposal, Directive, and Initiative across the
system is judged against it: a design that *grows* active context past the task is a
regression even when it looks quality-improving in isolation (a long-running session, reading
a whole artifact's prose, a single-shot do-the-whole-task prompt). When a design decision is
ambiguous, prefer the option that keeps the active context smaller and more relevant.

claude-orch-shell embodies it **at the extreme**: it reads *metadata only* (labels, state,
marker presence — never prose or code), routes through *durable artifacts* (Issues, labels)
rather than a live connection, and is *stateless* (fire-and-forget + metadata re-evaluation;
ephemeral spawns, no long-running session). The narrowest possible context for the
coordination job.

## What it does

- **Routes the Initiative** dir→eng: detects, from metadata alone, an Active unconsumed
  `initiative` Issue and proposes the handoff (`orch evaluate`).
- **Flags malformed artifacts** (label-exclusivity, missing required section) — structurally,
  without reading prose.
- **Proposes, never executes** — a human (or, when built, an opt-in mechanical invoke) acts.

## Success looks like

- **The metadata-only boundary holds.** No routing decision ever depends on artifact content;
  the routing core is structurally incapable of reading a body.
- **Handoffs are proposed at the right moment** — Active + unconsumed → propose; consumed →
  suppressed (no double-handoff); malformed → flagged, not routed.
- **No judgment leaks in.** Quality/strategy/implementation decisions stay in the stages.

## Out of scope

- **Not a commander** — never decides what an artifact should say or whether to pursue it.
- **Not a content reader** — metadata only; never source code, never prose.
- **Does not touch claude-eng-shell** — eng is a frozen external system, consumed only via the
  Initiative contract.

---

*Authoritative design: [SPEC.md](SPEC.md).*
