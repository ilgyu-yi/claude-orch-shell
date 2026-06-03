"""Offline tests for the claude-orch-shell routing core (orch SPEC §3/§4).

No third-party deps, no `gh`, no network. Run with:
    python3 routing/test_routing.py
or
    python3 -m unittest discover -s routing -p 'test_*.py'

Each test pins a row of the SPEC §3.1 routing table, plus the metadata-only
invariant (SPEC §4) and idempotency (SPEC §7).
"""

import unittest

from routing import (
    InitiativeMetadata,
    Rule,
    classify,
    evaluate,
    feedback_decisions,
)


def md(number=1, labels=("initiative",), state="open", close_reason=None,
       has_termination_header=True, consumer_count=0, title=""):
    return InitiativeMetadata(
        number=number,
        labels=frozenset(labels),
        state=state,
        close_reason=close_reason,
        has_termination_header=has_termination_header,
        consumer_count=consumer_count,
        title=title,
    )


class TestClassify(unittest.TestCase):
    def test_R1_active_unconsumed_proposes_handoff(self):
        d = classify(md(consumer_count=0))
        self.assertEqual(d.rule, Rule.R1_PROPOSE_HANDOFF)
        self.assertTrue(d.is_proposal)
        self.assertFalse(d.is_flag)

    def test_R2_active_with_consumer_is_in_progress(self):
        d = classify(md(consumer_count=1))
        self.assertEqual(d.rule, Rule.R2_IN_PROGRESS)
        self.assertFalse(d.is_proposal)

    def test_R3_blocked_no_handoff(self):
        d = classify(md(labels=("initiative", "status:blocked")))
        self.assertEqual(d.rule, Rule.R3_BLOCKED)
        self.assertFalse(d.is_proposal)

    def test_R4_proposed_no_handoff(self):
        d = classify(md(labels=("initiative", "status:proposed")))
        self.assertEqual(d.rule, Rule.R4_PROPOSED)
        self.assertFalse(d.is_proposal)

    def test_R4_other_status_label_is_not_active(self):
        # An unknown status:* label still means "not Active" -> no handoff (defensive).
        d = classify(md(labels=("initiative", "status:on-hold")))
        self.assertEqual(d.rule, Rule.R4_PROPOSED)
        self.assertFalse(d.is_proposal)

    def test_R5_closed_completed_is_terminal(self):
        d = classify(md(state="closed", close_reason="completed"))
        self.assertEqual(d.rule, Rule.R5_TERMINAL)
        self.assertFalse(d.is_proposal)

    def test_R5_closed_not_planned_is_terminal(self):
        d = classify(md(state="closed", close_reason="not-planned"))
        self.assertEqual(d.rule, Rule.R5_TERMINAL)

    def test_R6_label_exclusivity_flagged_first(self):
        # Even closed / consumed, co-present labels are surfaced as malformed.
        d = classify(md(labels=("initiative", "directive"), state="closed",
                        close_reason="completed", consumer_count=3))
        self.assertEqual(d.rule, Rule.R6_MALFORMED_LABELS)
        self.assertTrue(d.is_flag)
        self.assertFalse(d.is_proposal)

    def test_R7_active_missing_termination_header_is_malformed(self):
        d = classify(md(has_termination_header=False))
        self.assertEqual(d.rule, Rule.R7_MALFORMED_SECTION)
        self.assertTrue(d.is_flag)
        self.assertFalse(d.is_proposal)

    def test_R7_only_applies_when_active(self):
        # A proposed Initiative missing the header is R4 (gate not yet applied), not R7.
        d = classify(md(labels=("initiative", "status:proposed"), has_termination_header=False))
        self.assertEqual(d.rule, Rule.R4_PROPOSED)

    def test_skip_non_initiative(self):
        d = classify(md(labels=("directive",)))
        self.assertEqual(d.rule, Rule.SKIP_NOT_INITIATIVE)
        self.assertFalse(d.is_proposal)
        self.assertFalse(d.is_flag)

    def test_skip_unlabeled(self):
        d = classify(md(labels=()))
        self.assertEqual(d.rule, Rule.SKIP_NOT_INITIATIVE)


class TestMetadataOnlyInvariant(unittest.TestCase):
    def test_struct_has_no_body_or_code_field(self):
        # SPEC §4: the routing core must be unable to read content. Assert the
        # input dataclass exposes no body/content/prose/code field.
        forbidden = {"body", "content", "prose", "code", "text", "termination_condition"}
        fields = set(InitiativeMetadata.__dataclass_fields__.keys())
        self.assertEqual(fields & forbidden, set(),
                         f"metadata struct leaked a content field: {fields & forbidden}")

    def test_title_does_not_change_routing_decision(self):
        # Title is display-only (SPEC §3.3); it must not affect the rule.
        a = classify(md(title=""))
        b = classify(md(title="a totally different and longer title"))
        self.assertEqual(a.rule, b.rule)


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        self.repo = [
            md(1, consumer_count=0, title="ready"),                       # R1
            md(2, consumer_count=2, title="in progress"),                 # R2
            md(3, labels=("initiative", "status:blocked")),              # R3
            md(4, labels=("initiative", "directive")),                   # R6 flag
            md(5, has_termination_header=False),                          # R7 flag
            md(6, state="closed", close_reason="completed"),             # R5 report
            md(7, labels=("directive",)),                                # SKIP
        ]

    def test_proposals_only_from_R1(self):
        res = evaluate(self.repo)
        self.assertEqual([d.number for d in res.proposals], [1])

    def test_flags_are_R6_and_R7(self):
        res = evaluate(self.repo)
        self.assertEqual(sorted(d.number for d in res.flags), [4, 5])

    def test_reports_include_blocked_and_terminal(self):
        res = evaluate(self.repo)
        self.assertEqual(sorted(d.number for d in res.reports), [3, 6])

    def test_decisions_cover_every_input(self):
        res = evaluate(self.repo)
        self.assertEqual(len(res.decisions), len(self.repo))

    def test_idempotent(self):
        # SPEC §7: re-evaluating unchanged metadata yields the same proposals.
        first = evaluate(self.repo)
        second = evaluate(self.repo)
        self.assertEqual([d.number for d in first.proposals],
                         [d.number for d in second.proposals])
        # An already-consumed Initiative (R2) never yields a proposal -> no double handoff.
        self.assertNotIn(2, [d.number for d in first.proposals])


class TestFeedbackRouting(unittest.TestCase):
    """The upward eng->dir edge (SPEC §3.6, R8/R9)."""

    def test_R8_challenge_yields_proposal(self):
        ds = feedback_decisions(md(labels=("initiative", "initiative:challenged")))
        self.assertEqual([d.rule for d in ds], [Rule.R8_CHALLENGE])
        self.assertTrue(ds[0].is_proposal)

    def test_R9_completion_yields_proposal(self):
        ds = feedback_decisions(md(labels=("initiative", "initiative:completion-requested")))
        self.assertEqual([d.rule for d in ds], [Rule.R9_COMPLETION])
        self.assertTrue(ds[0].is_proposal)

    def test_both_labels_surface_both(self):
        ds = feedback_decisions(md(labels=("initiative", "initiative:challenged",
                                           "initiative:completion-requested")))
        self.assertEqual(sorted(d.rule.value for d in ds), ["R8", "R9"])

    def test_challenged_consumed_not_silently_ignored(self):
        # The load-bearing case: a challenged Initiative is already consumed (R2 by
        # classify), but evaluate must still surface it via R8 (SPEC §3.1 precedence).
        m = md(10, labels=("initiative", "initiative:challenged"), consumer_count=1)
        self.assertEqual(classify(m).rule, Rule.R2_IN_PROGRESS)        # base lifecycle
        res = evaluate([m])
        self.assertEqual([d.rule for d in res.proposals], [Rule.R8_CHALLENGE])  # surfaced

    def test_malformed_gets_no_feedback(self):
        # initiative+directive (R6) → no feedback routing.
        self.assertEqual(feedback_decisions(
            md(labels=("initiative", "directive", "initiative:challenged"))), ())

    def test_malformed_R7_missing_header_gets_no_feedback(self):
        # SPEC §3.1: "Malformed R6/R7 ... get no feedback routing." A challenged
        # Initiative missing its `## Termination condition` header (R7) must not
        # surface an R8/R9 handback — the malformed flag takes precedence, and a
        # termination assessment on a headerless Initiative is incoherent.
        self.assertEqual(feedback_decisions(
            md(labels=("initiative", "initiative:challenged"),
               has_termination_header=False, consumer_count=1)), ())
        self.assertEqual(feedback_decisions(
            md(labels=("initiative", "initiative:completion-requested"),
               has_termination_header=False, consumer_count=1)), ())

    def test_evaluate_R7_malformed_does_not_also_propose_feedback(self):
        # End-to-end: an R7-malformed, feedback-labelled Initiative surfaces ONLY
        # the malformed flag, never a feedback proposal (SPEC §3.1 precedence).
        m = md(7, labels=("initiative", "initiative:completion-requested"),
               has_termination_header=False, consumer_count=1)
        res = evaluate([m])
        self.assertEqual([d.rule for d in res.flags], [Rule.R7_MALFORMED_SECTION])
        self.assertEqual(res.proposals, ())

    def test_closed_gets_no_feedback(self):
        self.assertEqual(feedback_decisions(
            md(state="closed", close_reason="completed",
               labels=("initiative", "initiative:completion-requested"))), ())

    def test_non_initiative_gets_no_feedback(self):
        self.assertEqual(feedback_decisions(
            md(labels=("directive", "initiative:challenged"))), ())

    def test_evaluate_mixes_downward_and_upward(self):
        repo = [
            md(1, labels=("initiative",), consumer_count=0),                          # R1 (down)
            md(2, labels=("initiative", "initiative:challenged"), consumer_count=1),  # R8 (up)
            md(3, labels=("initiative", "initiative:completion-requested"), consumer_count=1),  # R9 (up)
        ]
        res = evaluate(repo)
        rules = sorted(d.rule.value for d in res.proposals)
        self.assertEqual(rules, ["R1", "R8", "R9"])


class TestValidation(unittest.TestCase):
    def test_bad_state_rejected(self):
        with self.assertRaises(ValueError):
            md(state="merged")

    def test_negative_consumer_count_rejected(self):
        with self.assertRaises(ValueError):
            md(consumer_count=-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
