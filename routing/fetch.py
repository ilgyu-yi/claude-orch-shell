"""Metadata fetcher — turn `gh issue` JSON into `InitiativeMetadata` for the
routing core (claude-orch-shell SPEC §2.1, §3.2).

This is the deliberately-SEPARATE piece the routing core depends on but does not
contain (SPEC §2.1): obtaining metadata is out of the routing core so the core can
never see a body. The fetcher *does* read issue bodies, but ONLY through fixed
regexes to compute marker/section **presence** (booleans) and `Parent Initiative:`
references (integers) — exactly the metadata operations the SPEC §2.1 whitelist
permits ("searching bodies for a fixed marker reads only marker presence, never
prose"). It returns `InitiativeMetadata` objects that carry **no body/prose**, so
no content ever reaches `classify`/`evaluate` (SPEC §2.2, §4).

`build_metadata(issues)` is pure and offline-testable (feed it parsed `gh --json`
output). `fetch_via_gh(repo)` is the thin live wrapper (shells out to `gh`); it is
not unit-tested here because it needs a real repo — its parsing is exercised via
`build_metadata` on fixtures.

Python 3 stdlib only. See routing/README.md.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter

from routing import InitiativeMetadata

# Fixed structural markers (SPEC §2.1, §3.2). These read PRESENCE / captured ints only.
_TERMINATION_HEADER = re.compile(r"^\s{0,3}#{2,3}\s+Termination condition\b", re.I | re.M)
_PARENT_INITIATIVE = re.compile(r"Parent Initiative:\s*#(\d+)", re.I)

# Fields the fetcher requests from `gh` — metadata + body (body used for marker
# presence only). SPEC §2.1.
GH_JSON_FIELDS = "number,title,labels,state,stateReason,body"

_STATE_REASON = {
    "COMPLETED": "completed",
    "NOT_PLANNED": "not-planned",
    None: None,
    "": None,
    "REOPENED": None,
}


def _labels_of(issue: dict) -> frozenset[str]:
    raw = issue.get("labels", []) or []
    names = []
    for lbl in raw:
        # gh --json gives label objects {name: ...}; tolerate bare strings too.
        names.append(lbl["name"] if isinstance(lbl, dict) else str(lbl))
    return frozenset(names)


def _state_of(issue: dict) -> str:
    s = (issue.get("state") or "").lower()
    if s not in ("open", "closed"):
        raise ValueError(f"issue #{issue.get('number')}: unexpected state {issue.get('state')!r}")
    return s


def _close_reason_of(issue: dict) -> str | None:
    sr = issue.get("stateReason")
    if isinstance(sr, str):
        sr = sr.upper()
    return _STATE_REASON.get(sr, None)


def build_metadata(issues: list[dict]) -> list[InitiativeMetadata]:
    """Pure transform: parsed `gh issue` JSON -> InitiativeMetadata list (SPEC §2.1).

    Consumer counts are computed across the WHOLE issue set (SPEC §3.2 scan scope:
    any state), since a consumer is usually a downstream (e.g. directive) issue, not
    an initiative. Bodies are read here only to compute presence + parent references
    and are NOT carried into the returned objects (SPEC §2.2, §4).
    """
    # Pass 1: count `Parent Initiative: #N` references across all issues' bodies.
    consumers: Counter[int] = Counter()
    for issue in issues:
        body = issue.get("body") or ""
        for m in _PARENT_INITIATIVE.finditer(body):
            consumers[int(m.group(1))] += 1

    # Pass 2: build one metadata record per issue (body discarded after presence checks).
    out: list[InitiativeMetadata] = []
    for issue in issues:
        body = issue.get("body") or ""
        number = int(issue["number"])
        md = InitiativeMetadata(
            number=number,
            labels=_labels_of(issue),
            state=_state_of(issue),
            close_reason=_close_reason_of(issue),
            has_termination_header=bool(_TERMINATION_HEADER.search(body)),
            consumer_count=consumers.get(number, 0),
            title=issue.get("title", "") or "",
        )
        out.append(md)
        # `body` goes out of scope here — it never enters InitiativeMetadata.
    return out


def fetch_via_gh(repo: str, *, states: str = "all", limit: int = 1000) -> list[InitiativeMetadata]:
    """Live path: shell out to `gh issue list` and build metadata (SPEC §2.1, §5).

    Not unit-tested (needs a real repo + `gh`); its JSON parsing is covered by
    build_metadata fixtures. `states='all'` covers open+closed per the SPEC §3.2
    consumer-scan scope.
    """
    cmd = [
        "gh", "issue", "list", "--repo", repo,
        "--state", states, "--limit", str(limit),
        "--json", GH_JSON_FIELDS,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    issues = json.loads(proc.stdout)
    return build_metadata(issues)


if __name__ == "__main__":
    # Demo over a synthetic `gh --json`-shaped fixture (no live gh).
    from routing import evaluate, render

    fixture = [
        {"number": 10, "title": "onboarding redesign", "state": "OPEN", "stateReason": None,
         "labels": [{"name": "initiative"}], "body": "## Termination condition\nactivation >= 40%"},
        {"number": 11, "title": "latency budget", "state": "OPEN", "stateReason": None,
         "labels": [{"name": "initiative"}], "body": "## Termination condition\np95 < 200ms"},
        {"number": 20, "title": "impl latency directive", "state": "OPEN", "stateReason": None,
         "labels": [{"name": "directive"}], "body": "Parent Initiative: #11\nwork..."},
    ]
    md = build_metadata(fixture)
    print(render(evaluate(md)))
