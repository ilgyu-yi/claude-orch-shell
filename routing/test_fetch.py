"""Offline tests for the metadata fetcher (orch SPEC §2.1, §3.2).

Feeds captured `gh issue list --json …`-shaped fixtures (no live `gh`, no network),
asserts the produced InitiativeMetadata and that the routing core then yields the
expected proposals/flags. Run with:
    python3 -m unittest discover -s routing -p 'test_*.py'   # from repo root
"""

import unittest

from fetch import build_metadata, GH_JSON_FIELDS
from routing import Rule, evaluate, classify


def issue(number, labels, state="OPEN", state_reason=None, body=""):
    return {
        "number": number,
        "title": f"issue {number}",
        "state": state,
        "stateReason": state_reason,
        "labels": [{"name": n} for n in labels],
        "body": body,
    }


TERM = "## Termination condition\nactivation >= 40% over a trailing 14-day window\n"


class TestBuildMetadata(unittest.TestCase):
    def test_parses_core_fields(self):
        md = build_metadata([issue(1, ["initiative"], body=TERM)])[0]
        self.assertEqual(md.number, 1)
        self.assertEqual(md.labels, frozenset({"initiative"}))
        self.assertEqual(md.state, "open")
        self.assertTrue(md.has_termination_header)
        self.assertEqual(md.consumer_count, 0)

    def test_state_and_close_reason_mapping(self):
        md = build_metadata([issue(1, ["initiative"], state="CLOSED",
                                   state_reason="COMPLETED", body=TERM)])[0]
        self.assertEqual(md.state, "closed")
        self.assertEqual(md.close_reason, "completed")
        md2 = build_metadata([issue(2, ["initiative"], state="CLOSED",
                                    state_reason="NOT_PLANNED")])[0]
        self.assertEqual(md2.close_reason, "not-planned")

    def test_termination_header_presence_only(self):
        with_header = build_metadata([issue(1, ["initiative"], body=TERM)])[0]
        without = build_metadata([issue(2, ["initiative"], body="## Problem\nstuff")])[0]
        self.assertTrue(with_header.has_termination_header)
        self.assertFalse(without.has_termination_header)

    def test_consumer_count_from_parent_marker_across_set(self):
        issues = [
            issue(11, ["initiative"], body=TERM),
            issue(20, ["directive"], body="Parent Initiative: #11\nwork"),
            issue(21, ["directive"], body="Parent Initiative: #11\nmore work"),
        ]
        md = {m.number: m for m in build_metadata(issues)}
        self.assertEqual(md[11].consumer_count, 2)
        self.assertEqual(md[20].consumer_count, 0)

    def test_consumer_marker_counts_closed_consumers_too(self):
        # SPEC §3.2: a closed consumer still evidences consumption began.
        issues = [
            issue(11, ["initiative"], body=TERM),
            issue(20, ["directive"], state="CLOSED", state_reason="COMPLETED",
                  body="Parent Initiative: #11"),
        ]
        md = {m.number: m for m in build_metadata(issues)}
        self.assertEqual(md[11].consumer_count, 1)

    def test_body_is_not_carried_into_metadata(self):
        # The metadata-only invariant (SPEC §2.2/§4): no body/prose on the struct.
        md = build_metadata([issue(1, ["initiative"], body="secret prose " + TERM)])[0]
        self.assertNotIn("body", md.__dataclass_fields__)
        # And no field value equals the body prose.
        for val in vars(md).values():
            self.assertNotIn("secret prose", str(val))

    def test_tolerates_bare_string_labels(self):
        raw = {"number": 1, "title": "x", "state": "OPEN", "stateReason": None,
               "labels": ["initiative"], "body": TERM}
        md = build_metadata([raw])[0]
        self.assertIn("initiative", md.labels)


class TestFetchThenRoute(unittest.TestCase):
    def setUp(self):
        self.issues = [
            issue(10, ["initiative"], body=TERM),                                  # R1 propose
            issue(11, ["initiative"], body=TERM),                                  # R2 (has consumer)
            issue(20, ["directive"], body="Parent Initiative: #11"),              # consumer + SKIP
            issue(30, ["initiative", "directive"], body=TERM),                    # R6 flag
            issue(40, ["initiative"], body="## Problem\nno termination header"),  # R7 flag
            issue(50, ["initiative"], state="CLOSED", state_reason="COMPLETED", body=TERM),  # R5
        ]

    def test_routing_over_fetched_metadata(self):
        res = evaluate(build_metadata(self.issues))
        self.assertEqual([d.number for d in res.proposals], [10])         # only R1
        self.assertEqual(sorted(d.number for d in res.flags), [30, 40])   # R6 + R7
        self.assertEqual(sorted(d.number for d in res.reports), [50])     # R5 terminal

    def test_consumed_initiative_is_in_progress_not_proposed(self):
        md = {m.number: m for m in build_metadata(self.issues)}
        self.assertEqual(classify(md[11]).rule, Rule.R2_IN_PROGRESS)


class TestContract(unittest.TestCase):
    def test_gh_json_fields_constant(self):
        # Guards against silently dropping a field the parser needs.
        for f in ("number", "title", "labels", "state", "stateReason", "body"):
            self.assertIn(f, GH_JSON_FIELDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
