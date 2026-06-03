"""claude-orch-shell routing core — pure, metadata-only classification.

Implements the type-A routing model of claude-orch-shell SPEC §3 (routing table)
under the metadata-only invariant of SPEC §4.

The load-bearing design choice (SPEC §4 item 1-2, §9 "Enforcement"): the routing
core is handed ONLY a metadata struct. `InitiativeMetadata` has NO body / prose /
code field, so reading artifact content here is *structurally impossible* — a
routing decision can only be a function of labels, state, close reason, and the
PRESENCE of fixed structural markers/sections. This file deliberately never
imports anything that could fetch a body; obtaining metadata (via `gh`) is a
separate, out-of-scope concern (SPEC §2.1, §5).

No third-party dependencies; Python 3 stdlib only. See routing/README.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Rule(str, Enum):
    """Routing outcomes, named to match the SPEC §3.1 routing table rows."""

    R1_PROPOSE_HANDOFF = "R1"   # Active + unconsumed -> propose dir->eng handoff
    R2_IN_PROGRESS = "R2"       # Active + has a Parent Initiative consumer -> in progress
    R3_BLOCKED = "R3"           # status:blocked -> no handoff
    R4_PROPOSED = "R4"          # status:proposed (manual path, gate not yet applied)
    R5_TERMINAL = "R5"          # closed (completed / not-planned) -> terminal
    R6_MALFORMED_LABELS = "R6"  # initiative AND directive co-present -> malformed flag
    R7_MALFORMED_SECTION = "R7"  # Active but a required section header is missing
    SKIP_NOT_INITIATIVE = "SKIP"  # not an initiative -> not the claude-orch-shell's concern


# Outcomes the claude-orch-shell surfaces as handoff PROPOSALS (SPEC §3.3).
PROPOSAL_RULES = frozenset({Rule.R1_PROPOSE_HANDOFF})
# Outcomes the claude-orch-shell surfaces as malformed-artifact FLAGS (SPEC §3.4).
FLAG_RULES = frozenset({Rule.R6_MALFORMED_LABELS, Rule.R7_MALFORMED_SECTION})
# Outcomes worth an optional rollup REPORT (SPEC §3, §7) — blocked / terminal.
REPORT_RULES = frozenset({Rule.R3_BLOCKED, Rule.R5_TERMINAL})


@dataclass(frozen=True)
class InitiativeMetadata:
    """The ONLY input the routing core may see (SPEC §2.1).

    Every field is metadata or a boolean/count derived from fixed-marker presence.
    There is deliberately NO body/content/code field — content reads are made
    structurally impossible (SPEC §4).
    """

    number: int
    labels: frozenset[str]
    state: str                       # "open" | "closed"
    close_reason: Optional[str] = None   # "completed" | "not-planned" | None
    has_termination_header: bool = True  # presence of "## Termination condition" (SPEC §2.1)
    consumer_count: int = 0          # # of Issues carrying `Parent Initiative: #<number>` (SPEC §3.2)
    # Display-only; MUST NOT influence the decision (kept out of `classify` logic).
    title: str = ""

    def __post_init__(self) -> None:
        if self.state not in ("open", "closed"):
            raise ValueError(f"state must be 'open' or 'closed', got {self.state!r}")
        if self.consumer_count < 0:
            raise ValueError("consumer_count must be >= 0")


@dataclass(frozen=True)
class RoutingDecision:
    number: int
    rule: Rule
    reason: str          # human-readable, references SPEC rule — metadata-derived only
    is_proposal: bool
    is_flag: bool
    title: str = ""      # passed through for the proposal message only (SPEC §3.3)


_STATUS_PREFIX = "status:"


def _active(md: InitiativeMetadata) -> bool:
    """Active = open AND no `status:*` label (SPEC §9; orch §3.1 R1)."""
    if md.state != "open":
        return False
    return not any(lbl.startswith(_STATUS_PREFIX) for lbl in md.labels)


def classify(md: InitiativeMetadata) -> RoutingDecision:
    """Map one Initiative's metadata to a routing decision (SPEC §3.1).

    Pure function of metadata only. Order of checks is significant: malformed
    label-exclusivity (R6) is surfaced before lifecycle routing so a structurally
    invalid artifact is always flagged.
    """
    has_initiative = "initiative" in md.labels
    has_directive = "directive" in md.labels

    # R6 — label exclusivity violation (SPEC §2.1, §3.4). Surfaced first.
    if has_initiative and has_directive:
        return RoutingDecision(
            md.number, Rule.R6_MALFORMED_LABELS,
            "carries both `initiative` and `directive` (labels are mutually exclusive)",
            is_proposal=False, is_flag=True, title=md.title,
        )

    # Not an Initiative -> outside the claude-orch-shell's concern (SPEC §3 graph).
    if not has_initiative:
        return RoutingDecision(
            md.number, Rule.SKIP_NOT_INITIATIVE,
            "not an `initiative` — not routed by the claude-orch-shell",
            is_proposal=False, is_flag=False, title=md.title,
        )

    # Closed -> terminal (SPEC §3.1 R5).
    if md.state == "closed":
        rsn = f"closed ({md.close_reason or 'unspecified'})"
        return RoutingDecision(
            md.number, Rule.R5_TERMINAL, f"terminal: {rsn}",
            is_proposal=False, is_flag=False, title=md.title,
        )

    # Open with a status:* label -> not Active.
    if "status:blocked" in md.labels:
        return RoutingDecision(
            md.number, Rule.R3_BLOCKED, "blocked (`status:blocked`) — no handoff",
            is_proposal=False, is_flag=False, title=md.title,
        )
    if "status:proposed" in md.labels:
        return RoutingDecision(
            md.number, Rule.R4_PROPOSED,
            "manual path (`status:proposed`) — commitment-bar gate not yet applied; not Active",
            is_proposal=False, is_flag=False, title=md.title,
        )
    # Any other status:* label -> defensively not Active, no handoff.
    if not _active(md):
        other = sorted(l for l in md.labels if l.startswith(_STATUS_PREFIX))
        return RoutingDecision(
            md.number, Rule.R4_PROPOSED,
            f"open but carries status label(s) {other} — not Active; no handoff",
            is_proposal=False, is_flag=False, title=md.title,
        )

    # ---- Active (open, no status:* label) ----
    # R7 — required-section presence is a structural (metadata) check (SPEC §2.1, §3.4).
    if not md.has_termination_header:
        return RoutingDecision(
            md.number, Rule.R7_MALFORMED_SECTION,
            "Active but missing a required `## Termination condition` header — malformed",
            is_proposal=False, is_flag=True, title=md.title,
        )

    # R2 — already being consumed (a downstream `Parent Initiative: #N` exists, SPEC §3.2).
    if md.consumer_count > 0:
        return RoutingDecision(
            md.number, Rule.R2_IN_PROGRESS,
            f"Active and already being consumed ({md.consumer_count} consumer(s)) — in progress",
            is_proposal=False, is_flag=False, title=md.title,
        )

    # R1 — Active and unconsumed -> propose dir->eng handoff.
    return RoutingDecision(
        md.number, Rule.R1_PROPOSE_HANDOFF,
        "Active and unconsumed — ready for eng to consume",
        is_proposal=True, is_flag=False, title=md.title,
    )


@dataclass(frozen=True)
class EvaluationResult:
    proposals: tuple[RoutingDecision, ...]
    flags: tuple[RoutingDecision, ...]
    reports: tuple[RoutingDecision, ...]
    decisions: tuple[RoutingDecision, ...]  # full per-initiative result (incl. R2/R4/SKIP)


def evaluate(repo_metadata: list[InitiativeMetadata]) -> EvaluationResult:
    """Pure evaluation over the target repo's metadata (SPEC §7).

    Idempotent: re-evaluating unchanged metadata yields the same result. A proposal
    is emitted only for R1 (Active + unconsumed), so an already-consumed Initiative
    (R2) never produces a duplicate handoff (SPEC §7 idempotency).
    """
    decisions = tuple(classify(md) for md in repo_metadata)
    proposals = tuple(d for d in decisions if d.rule in PROPOSAL_RULES)
    flags = tuple(d for d in decisions if d.rule in FLAG_RULES)
    reports = tuple(d for d in decisions if d.rule in REPORT_RULES)
    return EvaluationResult(proposals, flags, reports, decisions)


def render(result: EvaluationResult) -> str:
    """Render proposals/flags as the operator-facing output (SPEC §3.3, §7)."""
    lines: list[str] = []
    lines.append(f"Proposed handoffs ({len(result.proposals)}):")
    for d in result.proposals:
        label = f"#{d.number}" + (f" ({d.title})" if d.title else "")
        lines.append(f"  - {label}: {d.reason} [propose dir->eng]")
    lines.append(f"Malformed flags ({len(result.flags)}):")
    for d in result.flags:
        lines.append(f"  - #{d.number} [{d.rule.value}]: {d.reason}")
    if result.reports:
        lines.append(f"Reports ({len(result.reports)}):")
        for d in result.reports:
            lines.append(f"  - #{d.number} [{d.rule.value}]: {d.reason}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Tiny demo over synthetic metadata (no gh, no network).
    demo = [
        InitiativeMetadata(1, frozenset({"initiative"}), "open", title="onboarding redesign"),
        InitiativeMetadata(2, frozenset({"initiative"}), "open", consumer_count=2, title="latency budget"),
        InitiativeMetadata(3, frozenset({"initiative", "status:blocked"}), "open", title="vendor migration"),
        InitiativeMetadata(4, frozenset({"initiative", "directive"}), "open", title="malformed labels"),
        InitiativeMetadata(5, frozenset({"initiative"}), "open", has_termination_header=False, title="no termination header"),
        InitiativeMetadata(6, frozenset({"initiative"}), "closed", close_reason="completed", title="done thing"),
        InitiativeMetadata(7, frozenset({"directive"}), "open", title="someone else's artifact"),
    ]
    print(render(evaluate(demo)))
