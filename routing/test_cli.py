"""Offline tests for the orch CLI + config loader (SPEC §5.1, §7).

No `gh`, no network — the CLI's fetch step is injected with a stub fetcher.
Run with:
    python3 -m unittest discover -s routing -p 'test_*.py'   # from repo root
"""

import json
import unittest

from routing import InitiativeMetadata, Rule
from cli import run_evaluate, build_parser
from config import load_config, ShellEntry


def _md(number, labels=("initiative",), state="open", close_reason=None,
        has_termination_header=True, consumer_count=0, title=""):
    return InitiativeMetadata(
        number=number, labels=frozenset(labels), state=state, close_reason=close_reason,
        has_termination_header=has_termination_header, consumer_count=consumer_count, title=title,
    )


FIXTURE = [
    _md(10, title="onboarding", consumer_count=0),                         # R1 propose
    _md(11, title="latency", consumer_count=1),                            # R2
    _md(30, labels=("initiative", "directive")),                          # R6 flag
    _md(40, has_termination_header=False),                                 # R7 flag
    _md(50, state="closed", close_reason="completed"),                    # R5 report
]


def stub_fetcher(repo):
    return list(FIXTURE)


class _Out:
    def __init__(self):
        self.lines = []
    def __call__(self, *args):
        self.lines.append(" ".join(str(a) for a in args))
    @property
    def text(self):
        return "\n".join(self.lines)


class TestConfigLoader(unittest.TestCase):
    SAMPLE = """
target_repo: ilgyu-yi/example
shells:
  dir:
    path: ./claude-dir-shell
    invoke: "launch dir"
  eng:
    path: ./claude-eng-shell
    invoke: "launch eng"
  res:
    path: ./claude-res-shell
    invoke: null
auto_invoke: false
"""

    def test_parses_scalars(self):
        c = load_config(self.SAMPLE)
        self.assertEqual(c.target_repo, "ilgyu-yi/example")
        self.assertFalse(c.auto_invoke)

    def test_parses_shells(self):
        c = load_config(self.SAMPLE)
        self.assertEqual(c.shells["dir"], ShellEntry(path="./claude-dir-shell", invoke="launch dir"))
        self.assertEqual(c.shells["res"].invoke, None)        # null -> None
        self.assertEqual(set(c.shells), {"dir", "eng", "res"})

    def test_auto_invoke_true(self):
        c = load_config("target_repo: o/n\nauto_invoke: true\n")
        self.assertTrue(c.auto_invoke)

    def test_comments_and_blanks_ignored(self):
        c = load_config("# header\n\ntarget_repo: o/n   # inline comment\n")
        self.assertEqual(c.target_repo, "o/n")

    def test_empty_config_defaults(self):
        c = load_config("")
        self.assertIsNone(c.target_repo)
        self.assertFalse(c.auto_invoke)
        self.assertEqual(c.shells, {})


class TestRunEvaluate(unittest.TestCase):
    def test_text_output_lists_proposals_and_flags(self):
        out = _Out()
        res = run_evaluate("o/n", fetcher=stub_fetcher, out=out)
        self.assertEqual([d.number for d in res.proposals], [10])
        self.assertIn("target_repo=o/n", out.text)
        self.assertIn("propose-only", out.text)
        self.assertIn("#10", out.text)
        self.assertIn("Malformed flags (2)", out.text)

    def test_json_output_shape(self):
        out = _Out()
        run_evaluate("o/n", fetcher=stub_fetcher, as_json=True, out=out)
        doc = json.loads(out.text)
        self.assertEqual(doc["target_repo"], "o/n")
        self.assertEqual([p["number"] for p in doc["proposals"]], [10])
        self.assertEqual(sorted(f["number"] for f in doc["flags"]), [30, 40])
        self.assertEqual([r["number"] for r in doc["reports"]], [50])

    def test_repo_from_config_when_arg_absent(self):
        out = _Out()
        cfg = load_config("target_repo: cfg/repo\n")
        run_evaluate(None, config=cfg, fetcher=stub_fetcher, out=out)
        self.assertIn("target_repo=cfg/repo", out.text)

    def test_missing_repo_raises(self):
        with self.assertRaises(SystemExit):
            run_evaluate(None, fetcher=stub_fetcher, out=_Out())

    def test_auto_invoke_preview_without_spawner_does_not_launch(self):
        out = _Out()
        run_evaluate("o/n", fetcher=stub_fetcher, auto_invoke=True, out=out)
        self.assertIn("auto-invoke", out.text)
        self.assertIn("preview", out.text.lower())
        # R1 (dir->eng) is actuated by eng (SPEC §5.2.2).
        self.assertIn("eng (consume) #10", out.text)

    def test_auto_invoke_with_spawner_actuates(self):
        # With an injected spawner, auto-invoke actually actuates via the transport.
        from config import OrchConfig, ShellEntry
        from transport import SpawnOutcome
        calls = []
        def stub_spawner(task):
            calls.append(task)
            return SpawnOutcome(task=task, launched=True, detail="stub pid 1")
        cfg = OrchConfig(target_repo="o/n", auto_invoke=True, shells={
            "eng": ShellEntry(path="./e", invoke="claude-eng -p 'consume #{number} in {repo}'"),
        })
        out = _Out()
        run_evaluate("o/n", config=cfg, fetcher=stub_fetcher, auto_invoke=True,
                     spawner=stub_spawner, log_dir="/tmp/orch-logs", out=out)
        self.assertIn("launched 1", out.text)
        self.assertIn("eng-10-R1.log", out.text)        # transcript path surfaced
        self.assertNotIn("preview", out.text.lower())   # not the no-spawner path
        self.assertEqual([t.number for t in calls], [10])

    def test_auto_invoke_routes_feedback_to_dir_not_eng(self):
        # Regression: R8/R9 handbacks are actuated by dir, NOT eng (SPEC §5.2.2).
        feedback = [
            _md(10, title="onboarding", consumer_count=0),                                    # R1 -> eng
            _md(60, labels=("initiative", "initiative:challenged"), consumer_count=1),         # R8 -> dir
            _md(61, labels=("initiative", "initiative:completion-requested"), consumer_count=1),  # R9 -> dir
        ]
        out = _Out()
        run_evaluate("o/n", fetcher=lambda r: feedback, auto_invoke=True, out=out)
        self.assertIn("eng (consume) #10", out.text)
        self.assertIn("dir (review R8) #60", out.text)
        self.assertIn("dir (review R9) #61", out.text)
        # the feedback issues must NOT be labelled as an eng consume
        self.assertNotIn("eng (consume) #60", out.text)
        self.assertNotIn("Would invoke eng to consume", out.text)

    def test_idempotent_proposals(self):
        a = run_evaluate("o/n", fetcher=stub_fetcher, out=_Out())
        b = run_evaluate("o/n", fetcher=stub_fetcher, out=_Out())
        self.assertEqual([d.number for d in a.proposals], [d.number for d in b.proposals])


class TestParser(unittest.TestCase):
    def test_evaluate_parses_flags(self):
        ns = build_parser().parse_args(["evaluate", "o/n", "--json", "--auto-invoke"])
        self.assertEqual(ns.repo, "o/n")
        self.assertTrue(ns.json)
        self.assertTrue(ns.auto_invoke)

    def test_command_required(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main(verbosity=2)
