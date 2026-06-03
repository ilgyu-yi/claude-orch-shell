# routing/ — claude-orch-shell routing core (Tier-2 unit)

A reference implementation of claude-orch-shell's **metadata-only routing model**
(claude-orch-shell [SPEC.md](../SPEC.md) §3) under the **metadata-only invariant**
(SPEC §4). First Tier-2 unit; spec-conformant and offline-testable.

## What it is

- `cli.py` — the **`orch` CLI** (SPEC §7), propose-only. Wires `fetch_via_gh(repo)` →
  `evaluate` → `render`. The fetch step is injectable (`fetcher=`) so the CLI is
  offline-testable without `gh`. `auto_invoke` is acknowledged but the shell-launch
  transport is a deferred Tier-2 item (SPEC §5.2/§9), so it only *reports* what it would
  invoke. Run: `./bin/orch evaluate <owner/name>` (or `python3 routing/cli.py evaluate …`;
  `--config orch.config.yml`, `--json`, `--auto-invoke`).
- `config.py` — minimal loader for `orch.config.yml` (the SPEC §5.1 shell registry:
  `target_repo`, `shells` {path, invoke}, `auto_invoke`). Not a general YAML parser; see
  `orch.config.example.yml` at the repo root.
- `fetch.py` — the **metadata fetcher** (SPEC §2.1, §3.2), the deliberately-separate piece
  that turns `gh issue` JSON into `InitiativeMetadata` for the core.
  - `build_metadata(issues)` — pure transform of parsed `gh issue list --json …` output.
    Reads issue bodies **only** through fixed regexes to compute marker/section *presence*
    (`has_termination_header`) and `Parent Initiative: #N` references (`consumer_count`,
    counted across the whole set, any state, per §3.2). Returns `InitiativeMetadata` that
    carries **no body/prose** — so content never reaches the routing core (§2.2, §4).
  - `fetch_via_gh(repo)` — thin live wrapper (shells out to `gh`); not unit-tested (needs a
    real repo); its parsing is exercised via `build_metadata` fixtures.
- `routing.py`
  - `InitiativeMetadata` — the **only** input the routing core may see (SPEC §2.1). It
    has **no body / content / code field**, so reading artifact prose here is
    *structurally impossible* — this is how SPEC §4 (item 1–2) and §9 ("Enforcement")
    are operationalized, not merely promised.
  - `classify(md) -> RoutingDecision` — maps one Initiative's metadata to a routing
    outcome `R1…R7` / `SKIP`, exactly per the SPEC §3.1 routing table.
  - `evaluate(repo_md) -> EvaluationResult` — the pure evaluation over a repo's metadata
    (SPEC §7): `{proposals, flags, reports, decisions}`. Idempotent; only R1 (Active +
    unconsumed) emits a handoff proposal, so an already-consumed Initiative never
    double-hands-off.
  - `render(result)` — operator-facing text (SPEC §3.3).

## Rule ↔ SPEC mapping

| Rule | Metadata condition | Outcome |
|---|---|---|
| R1 | `initiative`, open, no `status:*`, `consumer_count == 0`, has termination header | **propose** dir→eng handoff |
| R2 | as R1 but `consumer_count > 0` | in progress (no proposal) |
| R3 | `initiative` + `status:blocked` | blocked (report) |
| R4 | `initiative` + `status:proposed` (or any other `status:*`) | not Active; no handoff |
| R5 | `initiative`, closed | terminal (report) |
| R6 | `initiative` **and** `directive` co-present | **flag** malformed (checked first) |
| R7 | Active but missing `## Termination condition` header | **flag** malformed |
| SKIP | not an `initiative` | not claude-orch-shell's concern |

## Scope / boundary (what this unit does NOT do)

- The **routing core** (`routing.py`) does not fetch metadata; the **fetcher** (`fetch.py`)
  does, and is kept separate so the core's `classify`/`evaluate` only ever see a body-less
  struct (SPEC §2.1, §4). The fetcher reads bodies solely for fixed-marker presence/counts.
- It does **not** invoke any shell (SPEC §5.2 transport, §6) or auto-execute handoffs
  (SPEC §3.3 default is propose-only). Those are later units.
- It makes **no** content/quality/strategy judgment (SPEC §1, §4, §6).

## Verify

```sh
python3 -m unittest discover -s routing -p 'test_*.py'   # from repo root — 31 tests
# or individually:
cd routing && python3 -m unittest test_routing -v        # routing core (21)
cd routing && python3 -m unittest test_fetch -v          # fetcher (10)
# demos (no gh, no network):
cd routing && python3 routing.py                          # routing over synthetic metadata
cd routing && python3 fetch.py                            # fetch (JSON fixture) -> route
```

`test_routing.py` (21) pins every routing-table row (R1–R7 + SKIP), the metadata-only
invariant (input struct exposes no content field; title cannot change a decision),
evaluation aggregation, idempotency (SPEC §7), and validation. `test_fetch.py` (10) pins the
`gh`-JSON parsing, the consumer-marker scan across the set (incl. closed consumers), that
the body is never carried into the metadata, and a fetch→route end-to-end path.

## Notes

- **Language is a provisional Tier-2 choice** (Python 3 stdlib): chosen for a clean pure
  function + structured fixtures with zero dependencies and no `gh`/network needed to
  test. Reversible — see WORK_LOG open question. eng-shell is bash-based but is frozen and
  out of scope; claude-orch-shell's stack is unconstrained.
