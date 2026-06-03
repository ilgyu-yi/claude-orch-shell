"""Offline tests for the subprocess transport (orch SPEC §5.2.1–§5.2.5).

No real process is ever launched — `spawner` is injected with a stub. Run with:
    python3 -m unittest discover -s routing -p 'test_*.py'   # from repo root
"""

import unittest

from routing import InitiativeMetadata, evaluate
from config import OrchConfig, ShellEntry
from transport import (
    plan_spawns,
    actuate,
    render_spawn_summary,
    SpawnTask,
    SpawnOutcome,
)


def _md(number, labels=("initiative",), state="open", close_reason=None,
        has_termination_header=True, consumer_count=0, title=""):
    return InitiativeMetadata(
        number=number, labels=frozenset(labels), state=state, close_reason=close_reason,
        has_termination_header=has_termination_header, consumer_count=consumer_count, title=title,
    )


CFG = OrchConfig(target_repo="o/n", auto_invoke=True, shells={
    "eng": ShellEntry(path="./claude-eng-shell",
                      invoke="claude-eng -p 'consume Initiative #{number} in {repo}'"),
    "dir": ShellEntry(path="./claude-dir-shell",
                      invoke="dir review-feedback {number} --repo {repo} --rule {rule}"),
    "res": ShellEntry(path="./claude-res-shell", invoke=None),
})

LOGS = "/tmp/orch-test-logs"


class _Spawner:
    """Records tasks; never launches anything."""
    def __init__(self):
        self.calls = []

    def __call__(self, task):
        self.calls.append(task)
        return SpawnOutcome(task=task, launched=True, detail="stub pid 1")


def _proposals_for(repo_md, cfg=CFG):
    return plan_spawns(evaluate(repo_md), cfg, repo="o/n", log_dir=LOGS)


class TestPlanSpawns(unittest.TestCase):
    def test_R1_maps_to_eng_consume(self):
        plan = _proposals_for([_md(10, title="onboarding")])
        self.assertEqual(len(plan.tasks), 1)
        t = plan.tasks[0]
        self.assertEqual(t.shell, "eng")
        self.assertEqual(t.action, "consume")
        self.assertEqual(t.number, 10)
        self.assertEqual(t.rule, "R1")
        self.assertEqual(t.argv[0], "claude-eng")
        self.assertIn("consume Initiative #10 in o/n", t.argv)
        self.assertTrue(t.log_path.endswith("eng-10-R1.log"))

    def test_R8_R9_map_to_dir_review(self):
        repo = [
            _md(60, labels=("initiative", "initiative:challenged"), consumer_count=1),
            _md(61, labels=("initiative", "initiative:completion-requested"), consumer_count=1),
        ]
        plan = _proposals_for(repo)
        by_num = {t.number: t for t in plan.tasks}
        self.assertEqual(set(by_num), {60, 61})
        self.assertTrue(all(t.shell == "dir" for t in plan.tasks))
        self.assertEqual(by_num[60].rule, "R8")
        self.assertEqual(by_num[61].rule, "R9")
        self.assertIn("review-feedback", by_num[60].argv)
        self.assertIn("--rule", by_num[60].argv)
        self.assertIn("R8", by_num[60].argv)
        self.assertIn("o/n", by_num[60].argv)

    def test_res_is_never_spawned(self):
        # A mixed repo with R1 + R8: no task ever routes to res (SPEC §5.2.2),
        # even though the registry has a res entry.
        repo = [
            _md(10),
            _md(60, labels=("initiative", "initiative:challenged"), consumer_count=1),
        ]
        plan = _proposals_for(repo)
        self.assertTrue(plan.tasks)
        self.assertFalse(any(t.shell == "res" for t in plan.tasks))

    def test_placeholders_fully_substituted(self):
        plan = _proposals_for([_md(42)])
        joined = " ".join(plan.tasks[0].argv)
        self.assertNotIn("{", joined)
        self.assertIn("#42", joined)
        self.assertIn("o/n", joined)

    def test_null_recipe_is_skipped_not_launched(self):
        cfg = OrchConfig(shells={"eng": ShellEntry(path="./e", invoke=None)})
        plan = plan_spawns(evaluate([_md(10)]), cfg, repo="o/n", log_dir=LOGS)
        self.assertEqual(plan.tasks, ())
        self.assertEqual(len(plan.skipped), 1)
        self.assertEqual(plan.skipped[0].number, 10)
        self.assertIn("recipe", plan.skipped[0].reason.lower())

    def test_missing_shell_in_registry_is_skipped(self):
        cfg = OrchConfig(shells={})  # no eng entry at all
        plan = plan_spawns(evaluate([_md(10)]), cfg, repo="o/n", log_dir=LOGS)
        self.assertEqual(plan.tasks, ())
        self.assertEqual(len(plan.skipped), 1)
        self.assertIn("eng", plan.skipped[0].reason)

    def test_no_config_skips_all(self):
        plan = plan_spawns(evaluate([_md(10)]), None, repo="o/n", log_dir=LOGS)
        self.assertEqual(plan.tasks, ())
        self.assertEqual(len(plan.skipped), 1)

    def test_no_proposals_no_tasks(self):
        # An already-consumed Initiative (R2) yields no proposal → nothing to spawn.
        plan = _proposals_for([_md(11, consumer_count=1)])
        self.assertEqual(plan.tasks, ())
        self.assertEqual(plan.skipped, ())


class TestActuate(unittest.TestCase):
    def test_fire_and_forget_one_call_per_task(self):
        repo = [
            _md(10),
            _md(60, labels=("initiative", "initiative:challenged"), consumer_count=1),
        ]
        plan = _proposals_for(repo)
        spawner = _Spawner()
        outcomes = actuate(plan.tasks, spawner=spawner)
        self.assertEqual(len(outcomes), len(plan.tasks))
        self.assertEqual([t.number for t in spawner.calls],
                         [t.number for t in plan.tasks])
        self.assertTrue(all(o.launched for o in outcomes))

    def test_actuate_does_not_read_child_output(self):
        # The stub returns no child output; actuate's result depends only on the
        # spawner's launched flag, never on parsing a result (fire-and-forget, §5.2.5).
        plan = _proposals_for([_md(10)])
        outcomes = actuate(plan.tasks, spawner=lambda t: SpawnOutcome(t, True, "launched"))
        self.assertEqual(len(outcomes), 1)
        self.assertTrue(outcomes[0].launched)

    def test_launch_failure_is_captured_not_raised(self):
        plan = _proposals_for([_md(10)])
        def failing(task):
            return SpawnOutcome(task, False, "launch failed: boom")
        outcomes = actuate(plan.tasks, spawner=failing)
        self.assertFalse(outcomes[0].launched)
        self.assertIn("failed", outcomes[0].detail)

    def test_empty_tasks_actuate_to_empty(self):
        self.assertEqual(actuate((), spawner=_Spawner()), ())


class TestRenderSummary(unittest.TestCase):
    def test_summary_lists_launched_and_skipped(self):
        cfg = OrchConfig(shells={
            "eng": ShellEntry(path="./e",
                              invoke="claude-eng -p 'consume #{number} in {repo}'"),
            # no dir entry → an R8 proposal is skipped
        })
        repo = [
            _md(10),
            _md(60, labels=("initiative", "initiative:challenged"), consumer_count=1),
        ]
        plan = plan_spawns(evaluate(repo), cfg, repo="o/n", log_dir=LOGS)
        outcomes = actuate(plan.tasks, spawner=_Spawner())
        text = render_spawn_summary(plan, outcomes)
        self.assertIn("eng", text)
        self.assertIn("#10", text)
        self.assertTrue(text.endswith("\n") or "transcript" in text.lower() or "log" in text.lower())
        self.assertIn("skip", text.lower())          # the dir R8 skip is surfaced
        self.assertIn("#60", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
