"""Subprocess transport — autonomous shell invocation (claude-orch-shell SPEC §5.2.1).

When `auto_invoke: true`, claude-orch-shell **actuates** a routing proposal by
ephemerally spawning the actuator shell for it (SPEC §5.2.2):

  - R1 (Active + unconsumed)  → spawn **eng** to *consume* Initiative #N
  - R8 / R9 (eng feedback)    → spawn **dir** to *review* the feedback for #N
  - res is **never** spawned by orch (SPEC §6).

The payload is **metadata only** — the target repo + the Initiative number + the
rule (SPEC §5.2.2); never artifact content. The spawn is **fire-and-forget**
(SPEC §5.2.5): orch does not block on or read the child's result in-band — the
shell leaves a metadata trail and the *next* `evaluate` routes on it (R2/R8/R9).

Each spawn's stdout/stderr is persisted to a per-task **transcript log**
(SPEC §5.2.4 observability). Safety (SPEC §5.2.3) comes from the spawned shell's
own hooks, not Claude prompts: orch does **not** add `--dangerously-skip-permissions`
— the operator's `invoke` recipe carries the sanctioned launch flags.

This module keeps the pure-core + injected-I/O discipline: `plan_spawns` is a pure
transform (EvaluationResult → tasks) and `actuate` takes an injected `spawner`, so
the whole thing is offline-testable without launching a process. `subprocess_spawner`
is the one impure piece (the real `Popen`), used only by the live CLI.

Python 3 stdlib only. See routing/README.md.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from routing import EvaluationResult, Rule

# rule → (actuator shell, action verb). The proposal rules are exactly R1/R8/R9
# (PROPOSAL_RULES, SPEC §3.1); res is absent by construction — it has no edge here.
_ACTUATORS = {
    Rule.R1_PROPOSE_HANDOFF: ("eng", "consume"),
    Rule.R8_CHALLENGE: ("dir", "review-challenge"),
    Rule.R9_COMPLETION: ("dir", "review-completion"),
}


@dataclass(frozen=True)
class SpawnTask:
    """One actuation to launch: a metadata-only payload pointed at a shell."""
    shell: str
    action: str
    number: int
    rule: str                  # routing rule value, e.g. "R1"
    argv: tuple[str, ...]      # the launch command, already split (no shell)
    log_path: str              # where the transcript is persisted (§5.2.4)


@dataclass(frozen=True)
class SpawnSkip:
    """A proposal that could not be actuated (no recipe / shell not registered)."""
    number: int
    rule: str
    shell: str
    reason: str


@dataclass(frozen=True)
class SpawnPlan:
    tasks: tuple[SpawnTask, ...]
    skipped: tuple[SpawnSkip, ...]


@dataclass(frozen=True)
class SpawnOutcome:
    task: SpawnTask
    launched: bool
    detail: str                # e.g. "pid 1234; transcript <path>" or a launch error


Spawner = Callable[[SpawnTask], SpawnOutcome]


def _fill(recipe: str, *, repo: str, number: int, rule: str) -> str:
    """Substitute the metadata-only placeholders into an invoke recipe.

    Explicit string replacement (not str.format) so the recipe may freely contain
    other braces/quotes without surprises.
    """
    return (recipe
            .replace("{repo}", repo)
            .replace("{number}", str(number))
            .replace("{rule}", rule))


def plan_spawns(
    result: EvaluationResult,
    config,                    # OrchConfig | None
    *,
    repo: str,
    log_dir: str,
) -> SpawnPlan:
    """Pure: turn an EvaluationResult's proposals into spawn tasks (SPEC §5.2.2).

    R1 → eng, R8/R9 → dir; res never appears. A proposal whose actuator shell has no
    `invoke` recipe (or is absent from the registry, or there is no config) is recorded
    as a skip rather than silently dropped.
    """
    shells = config.shells if config is not None else {}
    tasks: list[SpawnTask] = []
    skipped: list[SpawnSkip] = []

    for d in result.proposals:
        actuator = _ACTUATORS.get(d.rule)
        if actuator is None:
            # Defensive: a proposal rule with no actuator (should not happen).
            skipped.append(SpawnSkip(d.number, d.rule.value, "?",
                                     f"no actuator for rule {d.rule.value}"))
            continue
        shell, action = actuator
        entry = shells.get(shell)
        if entry is None:
            skipped.append(SpawnSkip(
                d.number, d.rule.value, shell,
                f"shell '{shell}' not in registry — cannot actuate"))
            continue
        if not entry.invoke:
            skipped.append(SpawnSkip(
                d.number, d.rule.value, shell,
                f"shell '{shell}' has no invoke recipe — cannot actuate"))
            continue
        argv = tuple(shlex.split(_fill(entry.invoke, repo=repo, number=d.number,
                                       rule=d.rule.value)))
        log_path = os.path.join(log_dir, f"{shell}-{d.number}-{d.rule.value}.log")
        tasks.append(SpawnTask(shell=shell, action=action, number=d.number,
                               rule=d.rule.value, argv=argv, log_path=log_path))

    return SpawnPlan(tasks=tuple(tasks), skipped=tuple(skipped))


def actuate(tasks, *, spawner: Spawner) -> tuple[SpawnOutcome, ...]:
    """Fire-and-forget: launch each task via the injected spawner (SPEC §5.2.5).

    Calls `spawner` once per task and collects its outcome. It never blocks on or
    reads a child's result in-band — the routing result comes from the *next*
    `evaluate` reading the metadata trail.
    """
    return tuple(spawner(task) for task in tasks)


def subprocess_spawner(task: SpawnTask) -> SpawnOutcome:
    """The real spawner: launch `task.argv` detached, transcript → `task.log_path`.

    - No `shell=` (argv is pre-split) so there is no shell-injection surface.
    - `start_new_session=True` detaches the child into its own process group, so orch
      does not wait on it (fire-and-forget, §5.2.5).
    - stdout+stderr are redirected to the transcript log (§5.2.4); stdin is closed.
    - orch adds **no** permission-bypass flag — those live in the operator's recipe
      (§5.2.3). Safety is the spawned shell's own hooks.

    Impure; not exercised by the offline tests (which inject a stub spawner).
    """
    try:
        os.makedirs(os.path.dirname(task.log_path) or ".", exist_ok=True)
        # The child inherits its own copy of the fd at spawn, so closing the parent's
        # handle afterwards does not truncate the child's stream.
        with open(task.log_path, "w", encoding="utf-8") as log:
            log.write(f"# orch transport: {task.shell} {task.action} "
                      f"#{task.number} ({task.rule})\n# argv: {list(task.argv)}\n")
            log.flush()
            proc = subprocess.Popen(
                list(task.argv),
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        return SpawnOutcome(task=task, launched=True,
                            detail=f"pid {proc.pid}; transcript {task.log_path}")
    except OSError as e:
        return SpawnOutcome(task=task, launched=False,
                            detail=f"launch failed: {e}")


def render_spawn_summary(plan: SpawnPlan, outcomes) -> str:
    """Operator-facing summary of an autonomous actuation pass (SPEC §5.2.4)."""
    launched = [o for o in outcomes if o.launched]
    failed = [o for o in outcomes if not o.launched]
    lines = [
        f"Subprocess transport (auto-invoke): launched {len(launched)}, "
        f"failed {len(failed)}, skipped {len(plan.skipped)} "
        f"(fire-and-forget; results flow back on the next evaluate, SPEC §5.2.5):"
    ]
    for o in launched:
        t = o.task
        lines.append(f"  - launched {t.shell} ({t.action}) #{t.number} [{t.rule}] "
                     f"— transcript {t.log_path} — {o.detail}")
    for o in failed:
        t = o.task
        lines.append(f"  - FAILED {t.shell} ({t.action}) #{t.number} [{t.rule}] "
                     f"— {o.detail}")
    for s in plan.skipped:
        lines.append(f"  - skipped #{s.number} [{s.rule}] — {s.reason}")
    return "\n".join(lines)
