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
