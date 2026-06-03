"""`orch` CLI — propose-only claude-orch-shell entry point (claude-orch-shell SPEC §7).

Wires the tested pieces together:  fetch_via_gh(repo) → evaluate → render
(SPEC §7 operation model). Propose-only by default (SPEC §3.3); `auto_invoke`
(config or --auto-invoke) is acknowledged but the shell-invocation transport is a
deferred Tier-2 open item (SPEC §5.2, §9), so this CLI reports what it WOULD invoke
rather than launching anything.

Usage:
    python3 routing/cli.py evaluate [REPO] [--config orch.config.yml] [--json] [--auto-invoke]

REPO (owner/name) may be given on the command line or via `target_repo` in the
config. The fetch step is injectable (`fetcher=`) so the CLI is offline-testable
without `gh`.

Python 3 stdlib only. See routing/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, Optional

from fetch import fetch_via_gh
from routing import InitiativeMetadata, Rule, evaluate, render, EvaluationResult

Fetcher = Callable[[str], list]


def _resolve_repo(arg_repo: Optional[str], config) -> str:
    repo = arg_repo or (config.target_repo if config else None)
    if not repo:
        raise SystemExit(
            "error: no target repo. Pass REPO (owner/name) or set `target_repo` in the config."
        )
    return repo


def _result_to_dict(repo: str, result: EvaluationResult, *, auto_invoke: bool) -> dict:
    return {
        "target_repo": repo,
        "auto_invoke": auto_invoke,
        "proposals": [
            {"number": d.number, "title": d.title, "rule": d.rule.value, "reason": d.reason}
            for d in result.proposals
        ],
        "flags": [
            {"number": d.number, "rule": d.rule.value, "reason": d.reason}
            for d in result.flags
        ],
        "reports": [
            {"number": d.number, "rule": d.rule.value, "reason": d.reason}
            for d in result.reports
        ],
    }


def run_evaluate(
    repo: Optional[str],
    *,
    config=None,
    as_json: bool = False,
    auto_invoke: bool = False,
    fetcher: Fetcher = fetch_via_gh,
    spawner=None,
    log_dir: str = ".orch/transcripts",
    out=print,
) -> EvaluationResult:
    """Core of `orch evaluate`, with an injectable fetcher (and spawner) for offline testing.

    With `auto_invoke` and an injected `spawner`, proposals are actuated via the
    subprocess transport (SPEC §5.2). Without a spawner (offline / preview), it only
    reports what it would spawn.
    """
    target = _resolve_repo(repo, config)
    metadata = fetcher(target)
    result = evaluate(metadata)

    if as_json:
        out(json.dumps(_result_to_dict(target, result, auto_invoke=auto_invoke), indent=2))
    else:
        out(f"claude-orch-shell · target_repo={target} · mode={'auto-invoke' if auto_invoke else 'propose-only'}")
        out(render(result))
        if auto_invoke:
            if spawner is not None:
                # Subprocess transport (SPEC §5.2): actuate the proposals. Each edge
                # has its own actuator — eng for R1 (consume), dir for R8/R9 feedback.
                from transport import plan_spawns, actuate, render_spawn_summary
                plan = plan_spawns(result, config, repo=target, log_dir=log_dir)
                outcomes = actuate(plan.tasks, spawner=spawner)
                out("")
                out(render_spawn_summary(plan, outcomes))
            else:
                # Preview (no spawner injected — e.g. offline): report, do not launch.
                eng_proposals = [d for d in result.proposals if d.rule is Rule.R1_PROPOSE_HANDOFF]
                dir_proposals = [d for d in result.proposals
                                 if d.rule in (Rule.R8_CHALLENGE, Rule.R9_COMPLETION)]
                if eng_proposals or dir_proposals:
                    out("\nauto-invoke preview (no spawner) — would invoke:")
                    for d in eng_proposals:
                        out(f"  - eng (consume) #{d.number}" + (f" ({d.title})" if d.title else ""))
                    for d in dir_proposals:
                        out(f"  - dir (review {d.rule.value}) #{d.number}" + (f" ({d.title})" if d.title else ""))
                else:
                    out("\nauto-invoke requested; no proposals to act on.")
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orch", description="Type-A claude-orch-shell (propose-only).")
    sub = p.add_subparsers(dest="command", required=True)
    ev = sub.add_parser("evaluate", help="Evaluate a target repo's Initiative metadata and propose dir->eng handoffs.")
    ev.add_argument("repo", nargs="?", default=None, help="Target repo owner/name (or set target_repo in config).")
    ev.add_argument("--config", default=None, help="Path to orch.config.yml.")
    ev.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    ev.add_argument("--auto-invoke", action="store_true",
                    help="Actuate proposals via the subprocess transport (SPEC §5.2; needs the one-time launcher sanction).")
    ev.add_argument("--log-dir", default=".orch/transcripts",
                    help="Where to persist per-spawn transcript logs (SPEC §5.2.4).")
    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "evaluate":
        config = None
        if args.config:
            from config import load_config_file
            config = load_config_file(args.config)
        auto = args.auto_invoke or bool(config and config.auto_invoke)
        # In auto-invoke mode the live CLI injects the real subprocess spawner; the
        # one-time launcher sanction (SPEC §5.2.3) is the OS permission rule allowing
        # the recipe binaries to run — orch adds no permission-bypass flag itself.
        spawner = None
        if auto:
            from transport import subprocess_spawner
            spawner = subprocess_spawner
        run_evaluate(args.repo, config=config, as_json=args.json, auto_invoke=auto,
                     spawner=spawner, log_dir=args.log_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
