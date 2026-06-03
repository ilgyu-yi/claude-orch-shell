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
from routing import InitiativeMetadata, evaluate, render, EvaluationResult

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
    out=print,
) -> EvaluationResult:
    """Core of `orch evaluate`, with an injectable fetcher for offline testing."""
    target = _resolve_repo(repo, config)
    metadata = fetcher(target)
    result = evaluate(metadata)

    if as_json:
        out(json.dumps(_result_to_dict(target, result, auto_invoke=auto_invoke), indent=2))
    else:
        out(f"claude-orch-shell · target_repo={target} · mode={'auto-invoke' if auto_invoke else 'propose-only'}")
        out(render(result))
        if auto_invoke:
            # Transport is a deferred Tier-2 open item (SPEC §5.2, §9): do NOT launch.
            if result.proposals:
                out("\nauto-invoke requested, but shell invocation is not yet implemented "
                    "(SPEC §5.2/§9). Would invoke eng to consume:")
                for d in result.proposals:
                    out(f"  - #{d.number}" + (f" ({d.title})" if d.title else ""))
            else:
                out("\nauto-invoke requested; no R1 proposals to act on.")
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orch", description="Type-A claude-orch-shell (propose-only).")
    sub = p.add_subparsers(dest="command", required=True)
    ev = sub.add_parser("evaluate", help="Evaluate a target repo's Initiative metadata and propose dir->eng handoffs.")
    ev.add_argument("repo", nargs="?", default=None, help="Target repo owner/name (or set target_repo in config).")
    ev.add_argument("--config", default=None, help="Path to orch.config.yml.")
    ev.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    ev.add_argument("--auto-invoke", action="store_true",
                    help="Request auto-invoke (transport not yet implemented; reports what it would invoke).")
    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "evaluate":
        config = None
        if args.config:
            from config import load_config_file
            config = load_config_file(args.config)
        auto = args.auto_invoke or bool(config and config.auto_invoke)
        run_evaluate(args.repo, config=config, as_json=args.json, auto_invoke=auto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
