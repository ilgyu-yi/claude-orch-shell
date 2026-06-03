# SPEC — claude-orch-shell

Canonical specification for the **claude-orch-shell**: the top-level component that coordinates
the three shells — **dir-shell** (planning tier, produces Initiatives), **eng-shell**
(execution tier, consumes Initiatives), and **res-shell** (on-demand research). The
claude-orch-shell is **type-A plumbing, not a commander**: it routes artifacts between stages
and *proposes* handoffs by reading **metadata only**; it never interprets artifact content
and never makes strategic or execution judgments.

- **Status**: Specification phase, fresh authoring. 2026-06-03.
- **Authority**: Source of truth for claude-orch-shell *design*. State/progress lives in
  `WORK_LOG.md` (same directory). Depends on the now-settled dir/res contracts
  (claude-dir-shell SPEC §4, §9 — the Initiative it routes; claude-res-shell SPEC §6.3 —
  res's invisibility to claude-orch-shell, its *only* dependency on res) — this SPEC routes
  over those real contracts, not guesses (the dir/res-contracts-first dependency).
- **Scope**: role + the type-A boundary (§1), the artifact/metadata surface it reads (§2),
  the routing model (§3), the metadata-only invariant (§4), shell location & invocation
  (§5), what it explicitly does not do (§6), operation model (§7), decision record (§8),
  open items (§9). Implementation is Tier 2; this SPEC is design-level.

> **Reading order.** §1 (boundary) → §3 (routing model) → §4 (metadata-only invariant) are
> the core. §2 defines exactly what it may read; §5 how it reaches the shells.

---

## 1. Role and the type-A boundary

```
        ┌──────────────────────── claude-orch-shell (type-A plumbing) ────────────────────────┐
        │  reads METADATA only · proposes handoffs · makes no strategic/execution judgment │
        └───────────────┬──────────────────────────────────────────────┬─────────────────┘
                        │ detects: Initiative Active (metadata)          │ proposes:
                        ▼                                                ▼  "Initiative #N ready for eng"
   ┌──────────┐   Initiative artifact (dir→eng contract)        ┌──────────┐
   │ dir-shell │ ───────────────────────────────────────────►  │ eng-shell │
   │ (planning)│                                                │(execution)│  [FROZEN/external]
   └────┬─────┘                                                 └────┬─────┘
        │ res call (strategic) — STAGE-INTERNAL,                     │ res call (technical) —
        ▼   invisible to claude-orch-shell                                ▼   STAGE-INTERNAL, invisible
   ┌──────────┐                                                 ┌──────────┐
   │ res-shell │  (claude-orch-shell neither sees nor routes res calls; §6)             │
   └──────────┘
```

claude-orch-shell's job is to notice, **from metadata alone**, when an artifact has reached
a state that makes it ready to move to the next stage, and to **propose** that move — in
**both** directions: dir→eng when an Initiative is ready to consume (R1), and eng→dir when
eng surfaces a challenge/completion on it (R8/R9, §3.6). It is "plumbing": it connects
stages and lets artifacts flow; it is not a "commander" that decides *what* the artifacts
should say or *whether* the strategy/execution is sound.

**Type-A means, precisely:**

- It reads **metadata** — labels, issue state, close reason, and the **presence** of fixed
  structural markers (§2) — never the prose content of an artifact.
- It **proposes** stage transitions (handoffs); it does not author downstream artifacts
  (no Directives, no Initiatives) and does not perform a stage's internal work.
- It makes **no judgment** about quality, strategy, or implementation. Quality gates live
  in the stages (dir's commitment-bar termination-condition gate, dir SPEC §3.4; eng's own
  review flow). claude-orch-shell **trusts** those gates via the metadata they leave behind.

---

## 2. The artifact/metadata surface

claude-orch-shell operates over a **target repo** (referenced by `owner/name`, read via `gh`
— local, no remotes of its own) and/or a workspace. The **only** things it may read:

### 2.1 Allowed metadata (the whole read surface)

| Metadatum | Source | Example |
|---|---|---|
| **Labels** | `gh issue` labels | `initiative`, `directive`, `status:proposed`, `status:blocked`, `initiative:challenged`, `initiative:completion-requested` |
| **Issue state** | open / closed | `open` |
| **Close reason** | `completed` / `not-planned` | `completed` |
| **Structural-marker presence** | a fixed regex match against the body, yielding only a boolean / a captured issue number — **never the surrounding prose** | does `Parent Initiative: #N` exist, and what is `N`? |
| **Required-section presence** | boolean: does a required `## <Section>` header exist | is there a `## Termination condition` header? (presence only — **not** its text) |
| **Issue enumeration by metadata** | `gh issue list` filtered by label/state | "all Issues with label `initiative`"; "all Issues whose body contains a `Parent Initiative:` marker" |

"Required-section presence" is a metadata-level check (a header exists / does not) used only
to detect a **malformed** artifact (§3.4). claude-orch-shell must **not** read what the
section *says* — judging the termination condition's validity is dir's gate (dir SPEC §3.4),
not claude-orch-shell's.

**Enumeration is a metadata operation.** Listing Issues by label/state and searching bodies
for a fixed marker (`gh issue list --label …`, `gh search issues 'Parent Initiative:'`)
reads only labels/state and marker presence — never prose — so it stays within the read
whitelist (§4). It is the primitive the consumer-marker scan (§3.2) is built on.

### 2.2 Forbidden reads

claude-orch-shell must **never** read or act on: the Summary/Problem/Current state prose,
the **text** of the termination condition, success signals, any free-text body content, or
any source code. If a routing decision would require interpreting prose, it is **out of
scope** — the decision belongs to a stage, not claude-orch-shell (§4).

---

## 3. The routing model (metadata-level)

claude-orch-shell evaluates the metadata surface (§2) and emits a set of **proposed
transitions**. The graph of inter-stage edges it cares about is deliberately small — **two
edges, both carried by the Initiative**:

- **dir → eng** (downward): an Active, unconsumed Initiative is ready for eng to consume
  (R1, §3.2).
- **eng → dir** (upward): eng surfaced a **challenge** or **completion** on the Initiative;
  the signal is routed back to dir to adjudicate (R8/R9, §3.6).

(res is out of scope, §6; eng's internal Directive→execution flow is below the contract
boundary and eng-internal, §3.5.)

### 3.1 The routing table

Anchored on the real contracts (dir SPEC §4 = what a consumable Initiative carries; dir SPEC
§9 = Initiative lifecycle states):

| # | Artifact metadata state | claude-orch-shell action |
|---|---|---|
| R1 | `initiative` label · open · no `status:*` label (**Active**, dir SPEC §9) · no downstream consumer marker (§3.2) | **Propose dir→eng handoff**: "Initiative #N is Active and unconsumed — ready for eng to consume." |
| R2 | `initiative` · open · **has** ≥1 downstream `Parent Initiative: #N` consumer (§3.2) | **No action** — already being consumed (in progress). |
| R3 | `initiative` · `status:blocked` | **No handoff.** Optionally surface in a "blocked" report. |
| R4 | `initiative` · `status:proposed` (manual path; dir SPEC §11) | **No handoff** — the commitment-bar gate has not yet been *applied* to this filing (deferred to review per dir SPEC §11); it is not yet Active. |
| R5 | `initiative` · closed (`completed` or `not-planned`) | **No handoff** (terminal). Optionally record in a "completed/closed" report. |
| R6 | `initiative` **and** `directive` labels co-present | **Flag malformed** (label-exclusivity violation, §3.4). No handoff. |
| R7 | `initiative` · open · Active · **missing a required `## Section` header** (§2.1) | **Flag malformed** (§3.4). No handoff until dir fixes it. |
| R8 | `initiative` · open · **`initiative:challenged`** label present (§3.6) | **Propose eng→dir handback**: "Initiative #N has an eng challenge — dir re-evaluation requested." |
| R9 | `initiative` · open · **`initiative:completion-requested`** label present (§3.6) | **Propose eng→dir handback**: "Initiative #N reported execution-complete by eng — dir termination assessment requested." |

**Precedence.** Evaluate in this order: malformed flags (R6, R7) → **feedback (R8, R9)** →
lifecycle (R1–R5). The feedback labels must be checked **before** R1/R2, because a
challenged/completed Initiative is necessarily already consumed (eng worked on it) and would
otherwise fall to R2 ("in progress") and be silently ignored — R8/R9 surface it for dir.
R8 and R9 are independent; if both labels are present, surface both (dir handles each). The
feedback labels are `initiative:*`, not `status:*`, so they do not by themselves change the
"Active" determination (§9) — R8/R9 fire on an open Initiative carrying the label regardless
of its lifecycle state.

### 3.2 Detecting "already consumed" (metadata only)

An Initiative `#N` is "being consumed" iff there exists at least one other Issue in the
target repo whose body contains the structural marker `Parent Initiative: #N`. This is a
pure metadata/marker check (regex presence + captured number), reading no prose. It is how
R1 vs R2 is decided without judging anything. (The downstream consumer is typically an
eng-shell `directive`-labeled Issue, but claude-orch-shell only checks the marker, not the
consumer's tier.)

**Scan scope.** The consumer scan covers Issues in **any state** (open *and* closed) — a
closed Directive still evidences that consumption began, so a closed consumer suppresses a
re-handoff (R2). Implemented via the enumeration primitive (§2.1): `gh search issues
'Parent Initiative: #N' --repo <target>` (or a one-time `gh issue list` + marker filter),
not a body-by-body prose read. Enumeration cost/scale is an open item (§9).

### 3.3 Proposal, not execution

For R1, claude-orch-shell's output is a **proposal** — surfaced to the human and/or the eng
stage — of the form: *"Initiative #N (`<title>`) is Active and unconsumed; hand off to
eng-shell?"* It carries only metadata (number, title, labels, state). claude-orch-shell:

- **may** mechanically **invoke** the eng stage to *begin* consumption (a transport action —
  see §5), if the operator has enabled auto-invocation;
- **must not** perform the consumption itself: it never authors a Directive, never decides
  *how* to decompose the Initiative, never evaluates whether the Initiative is worth doing.
  Those are eng's execution judgments (§6).

Default is **propose-only**; auto-invocation is opt-in config (§7).

### 3.4 Malformed-artifact flagging (R6, R7)

These are **metadata-integrity** flags, not content judgments: label exclusivity (dir SPEC
§2.1) and required-section presence (§2.1) are structural facts. claude-orch-shell surfaces
the violation ("Initiative #N carries both `initiative` and `directive`"; "Initiative #N is
Active but has no `## Termination condition` header") and proposes **no handoff** until a
stage fixes it. It does not fix the artifact itself (that would be authoring content).

### 3.5 Why the graph is small (and eng-internal flow is out of scope)

eng consumes an Initiative and, internally, produces Directives → execution → merges. All
of that is **below the dir→eng contract boundary** and is eng-shell's own concern (eng is a
frozen external system, dir SPEC §10). claude-orch-shell does **not** route inside eng. Its
edges are the two **inter-stage** ones (§3): dir→eng (R1) and eng→dir (R8/R9). Any further
cross-tier edge requires a settled contract first; it would be added here as a new rule,
recorded in §8/§9 — not invented ahead of the contract.

### 3.6 Upward routing: eng→dir feedback (challenge / completion)

The Initiative contract is two-way: dir guarantees a code-independent, evaluable termination
condition (dir SPEC §3–§4); eng, from the execution layer, can report back that execution
**contradicts** the Initiative (a *challenge*) or that the work has **landed** (a
*completion*). claude-orch-shell routes that signal back to dir, which adjudicates.

**The signal is a label — eng stays frozen and comment-only.** eng's `/initiative-feedback`
posts a **comment-only** finding led by a scannable marker (`## Initiative challenge` /
`## Initiative completion`) and never edits/relabels/closes the Initiative (`initiative-
readonly`). A **target-repo substrate Action** (§5.4) converts that comment marker into a
label:

| eng comment marker | label the Action adds |
|---|---|
| `## Initiative challenge` | `initiative:challenged` |
| `## Initiative completion` | `initiative:completion-requested` |

claude-orch-shell then reads **only the label** (a pure metadata read, already in the §2.1
"Labels" surface — it never reads the challenge/completion prose; that reasoning is dir's to
judge).

**The handshake — four roles, no shared state, no timestamps:**

- **Action adds** the label, event-driven on a *new* comment (`issue_comment.created`), so it
  never re-adds a label after dir has cleared it.
- **dir reads the comment, judges, and removes the label** when handled (challenge →
  revise / defend / retire; completion → evaluate the termination condition and close, or
  post that more is needed — dir SPEC, forthcoming). Removing the label is the "handled"
  signal; the upward route clears automatically.
- **claude-orch-shell reads** label presence and **proposes**; it never adds or removes a
  label (it is a metadata reader, not a writer).
- **eng comments only** (unchanged; frozen).

**Fail-open.** If the substrate Action (§5.4) is not installed in the target repo, the
labels never appear and claude-orch-shell simply emits no upward proposals — the eng
comments still exist for a human to act on. No breakage; the downward edge is unaffected.

This keeps every invariant: claude-orch-shell stays metadata-only and propose-only (§4); the
*judgment* on a challenge/completion is dir's (the label is a routing trigger, not a verdict);
eng is unchanged. The choice of labels-derived-by-Action over eng-emitted labels is decision
O10 (§8).

---

## 4. The metadata-only invariant

The single load-bearing property of a type-A claude-orch-shell. Stated so it can later be
enforced (Tier 2) and tested:

1. **Read whitelist.** claude-orch-shell's reads are confined to §2.1. Any read of free-text
   body prose or source code is a defect.
2. **Decisions are functions of metadata only.** Every routing action (§3) is determined
   solely by labels, state, close reason, and fixed-marker/section **presence**. If a
   proposed action cannot be derived from those, claude-orch-shell must **not** take it —
   it defers to a stage.
3. **No content interpretation, ever** — including the termination condition. The
   claude-orch-shell trusts that an Active Initiative passed dir's gate (dir SPEC §3.4); it does
   not re-judge it. (It *may* check the `## Termination condition` header *exists*, §2.1 —
   presence is metadata; meaning is not.)
4. **No strategic/execution judgment.** It never decides whether an Initiative is good,
   whether it should be pursued, or how it should be implemented (§6).
5. **res is invisible.** It never observes, triggers, or routes a res call (§6, res SPEC
   §6.3).

A Tier-2 implementation should make violations detectable (e.g., the routing core is handed
only a metadata struct — never the raw body — so content-reading is structurally
impossible; §9).

---

## 5. Shell location and invocation (design level, local)

All local; no remotes. claude-orch-shell must be able to **locate** each shell as a
component and **invoke** it.

### 5.1 Shell registry

A config (top-level, e.g. `orch.config.yml`) maps each shell to its tool-repo path and an
invocation recipe:

```yaml
target_repo: owner/name          # the repo whose Initiative metadata is routed (gh, local)
shells:
  dir:
    path: ./claude-dir-shell     # tool repo (today a sibling dir; later a submodule)
    invoke: "<recipe to launch dir-shell against target_repo / a workspace>"
  eng:
    path: ./claude-eng-shell     # FROZEN external system — invoked read-as-contract only
    invoke: "<recipe to launch eng-shell to consume Initiative #N>"
  res:
    path: ./claude-res-shell
    invoke: null                 # not invoked by claude-orch-shell (res is stage-internal, §6)
auto_invoke: false               # propose-only by default (§3.3, §7)
```

Paths are the three sub-repo directories today and become **submodules** later (working
brief §1) — the registry shape is unchanged by that migration; only resolution of `path`
changes. claude-orch-shell does not embed shell internals; it holds a path + a recipe.

### 5.2 Invocation = transport, not judgment

"Invoke a shell" means: launch that shell's Claude Code context (a local session/process)
pointed at the target repo or a workspace, handing it **metadata** (e.g., "consume
Initiative #N"). The shell then does its own work under its own gates. claude-orch-shell's
involvement ends at launch; it does not steer the shell's internal decisions. The concrete
launch mechanism (subprocess, session hand-off) is a Tier-2 choice (§9), parallel to res's
own invocation-mechanism open item (res SPEC §10).

### 5.3 eng is invoked as a frozen contract

eng-shell is frozen/out of scope (dir SPEC §10). claude-orch-shell may
**invoke** eng (transport) and **read** eng-produced metadata (the `Parent Initiative: #N`
marker, §3.2; the `## Initiative challenge|completion` comment markers, surfaced as labels
by §5.4), but never modifies eng-shell and assumes nothing about eng's internals beyond the
published contract. **No claude-orch-shell feature requires an eng-shell change** — the
upward edge (§3.6) is built on eng's *existing* comment markers plus a target-repo Action
(§5.4), specifically so eng stays frozen (decision O10, §8).

### 5.4 Required target-repo substrate: the feedback-label Action

The upward edge (§3.6) depends on one piece of **target-repo substrate** — a GitHub Action
(`initiative-feedback-label.yml`, installed at onboarding alongside the other dir-mode
workflows):

- **Trigger**: `issue_comment` (`created`).
- **Behavior**: if the new comment's body begins with `## Initiative challenge`, add the
  `initiative:challenged` label to the issue; if `## Initiative completion`, add
  `initiative:completion-requested`. Idempotent (adding an existing label is a no-op).
  Event-driven on *new* comments only — it never re-scans history, so it does not re-add a
  label dir has removed.
- **Why it lives in the target repo, not in eng or orch**: it converts eng's *published*
  comment contract into a routing label without touching eng (frozen) and without
  claude-orch-shell writing to artifacts (it stays a metadata reader). This mirrors
  eng-shell's own `auto-status-proposed.yml` pattern.

claude-orch-shell treats this Action as **optional substrate**: absent it, no labels appear
and the upward edge is simply inactive (fail-open, §3.6) — the eng comments remain for a
human. Implementing the Action is a Tier-2 item (§9).

---

## 6. What claude-orch-shell explicitly does NOT do

- **Does not read content** — no prose, no termination-condition text, no code (§2.2, §4).
- **Does not judge** — not Initiative quality, not strategy, not whether to pursue, not how
  to implement. Stages own their gates (§1; §4 invariant item 4).
- **Does not author artifacts** — never writes an Initiative or a Directive; never edits an
  artifact to fix it (it flags, §3.4).
- **Does not see or route res calls** — research requests/documents are stage-internal
  subroutines of dir/eng (res SPEC §6.3; dir SPEC §14 D11). claude-orch-shell has no res edge.
- **Does not route inside a stage** — eng's Directive→execution flow is eng-internal (§3.5).
- **Does not run autonomously by default** — it proposes; a human or, if enabled, a
  mechanical auto-invoke acts (§3.3, §7).

---

## 7. Operation model

claude-orch-shell is best understood as a **pure evaluation over current metadata**:

```
evaluate(target_repo_metadata) → { proposed_handoffs[], malformed_flags[], reports[] }
```

- **Stateless w.r.t. content**: it reads the current metadata surface (§2) each run and
  derives proposals; it holds no opinion carried over from prior content.
- **Invoked, not daemon**: run on demand ("what's ready to route?") or on a metadata-change
  trigger (e.g., an Issue labeled/closed). It is not required to run continuously.
- **Output is proposals + flags + optional reports** (blocked/completed rollups, §3). With
  `auto_invoke: true`, R1 proposals additionally trigger a mechanical eng invocation (§5.2);
  otherwise they are surfaced for a human to action.
- **Idempotent**: re-evaluating unchanged metadata yields the same proposals; a proposal
  for an already-consumed Initiative (R2) is suppressed, so re-runs don't double-hand-off.

---

## 8. Decision record

**[brief]** marks premises from the working brief §3 (fixed unless proven to block the end
goal, then revise-and-log per brief §2.4).

| # | Decision | Rationale |
|---|---|---|
| O1 **[brief]** | claude-orch-shell is **type-A plumbing**: routes artifacts, proposes handoffs, reads **metadata only**, makes **no** strategic/execution judgment (§1). | The brief fixes this. Keeps judgment in the stages (where the gates and code knowledge live) and keeps claude-orch-shell simple and trustworthy. |
| O2 **[brief]** | Reads **metadata only, never content** (§2, §4); even the termination condition is read for header **presence**, never meaning. | The brief's load-bearing constraint. Content interpretation would make claude-orch-shell a commander and couple it to artifact semantics. It trusts dir's gate instead of re-judging. |
| O3 | The routing graph has **two inter-stage edges, both via the Initiative: dir→eng (R1) and eng→dir feedback (R8/R9)** (§3, §3.5, §3.6). eng-internal flow and res calls are out of scope. | Both ride a *settled* contract: the downward edge on the Initiative dir guarantees (dir SPEC §4), the upward edge on eng's *existing* `## Initiative challenge\|completion` markers. No new cross-tier edge is invented ahead of a contract. |
| O4 | "Ready to hand off" = `initiative` · open · no `status:*` · no `Parent Initiative: #N` consumer (R1); "in progress" = has such a consumer (R2) (§3.1–§3.2). | All derivable from labels/state + a fixed marker presence — pure metadata, satisfying O2. Mirrors dir SPEC §9 (Active) and the §4.3 linkage marker. |
| O5 **[brief]** | **Propose, don't execute** (§3.3): may mechanically *invoke* a shell (transport) but never performs a stage's internal work or judgment; auto-invoke is opt-in. | "Plumbing not commander." Mechanically moving an artifact along is transport; deciding what it means or how to implement it is the stage's. |
| O6 **[brief]** | **res is invisible** to claude-orch-shell (§6). | res calls are stage-internal subroutines (res SPEC §6.3; dir SPEC §14 D11). |
| O7 | Shells are located via a **registry** (path + invocation recipe), with paths that become submodules later without changing the registry shape (§5.1). | Keeps claude-orch-shell decoupled from shell internals and survives the planned submodule promotion (brief §1). |
| O8 | Malformed-artifact handling is **flag-only** (R6, R7, §3.4): surface label-exclusivity / required-section-presence violations, propose no handoff, never auto-fix. | Structural integrity is metadata-checkable (O2-safe); fixing would be authoring content (violates O5). |
| O9 | Operation is a **pure evaluation over metadata** → proposals/flags/reports; invoked, idempotent, not a daemon (§7). | Makes the metadata-only invariant (§4) structurally enforceable and re-runs safe. |
| O10 | The eng→dir feedback signal is a **label derived from eng's comment marker by a target-repo Action** (§3.6, §5.4) — **not** a label eng emits itself. | Single source of truth: the label is a deterministic projection of eng's comment, so the two can't drift. eng stays unaware of the routing vocabulary (no abstraction leak) and **unchanged** (frozen) — routing-vocabulary changes never touch eng. Mirrors eng's own `auto-status-proposed.yml`. Chosen over option A (eng emits the label), which would require unfreezing eng and couple it to the protocol. |
| O11 | The feedback **handshake** is: Action **adds** the label (new-comment event), dir **removes** it after handling, claude-orch-shell **reads** presence, eng **comments** only (§3.6). | A clean four-role split with no shared state and no timestamps. Label removal is the "handled" signal that clears the upward route; claude-orch-shell stays a read-only metadata router. |

---

## 9. Open items

- **Concrete invocation mechanism** (§5.2): how claude-orch-shell launches a shell locally
  (subprocess vs session hand-off). Decide at Tier 2; parallel to res SPEC §10.
- **Trigger model** (§7): on-demand only, vs a metadata-change hook (e.g., a target-repo
  Issue-event watcher). Likely on-demand first.
- **Enforcement of the metadata-only invariant** (§4): ✅ **implemented** in
  [`routing/`](routing/) (Tier-2) — `classify`/`evaluate` are handed only an
  `InitiativeMetadata` struct that has no body/content field, so content reads are
  structurally impossible; a test asserts the struct exposes no content field and that the
  title cannot change a decision.
- **Metadata fetcher** (§2.1, §3.2): ✅ **pure core implemented** in
  [`routing/fetch.py`](routing/) — `build_metadata(gh_json)` parses `gh issue list --json`
  output into `InitiativeMetadata`, reading bodies only for fixed-marker presence
  (`has_termination_header`) and `Parent Initiative: #N` counts (any state, §3.2); the body
  never enters the returned struct. Offline-tested on JSON fixtures (a fetch→route path).
  Still open: the live `fetch_via_gh` wrapper is untested (needs a real repo) and the
  enumeration cost/scale at large repos (§3.2).
- **Operation entry point / CLI** (§7): ✅ **implemented (propose-only)** in
  [`routing/cli.py`](routing/) + [`bin/orch`](bin/orch) — `orch evaluate <repo>` wires
  `fetch_via_gh → evaluate → render` (text or `--json`). Offline-tested via an injected
  fetcher. `--auto-invoke` is recognized but only *reports* what it would invoke (transport
  deferred, §5.2). Live `gh` path verified by documented manual check.
- **Config format/location** (§5.1): ✅ **minimal loader implemented** in
  [`routing/config.py`](routing/) with an example [`orch.config.example.yml`](orch.config.example.yml)
  (`target_repo`, `shells`{path,invoke}, `auto_invoke`). Still open: swap the minimal parser
  for real YAML if configs grow.
- **Shell invocation transport** (§5.2): the concrete launch mechanism (subprocess / session
  hand-off) for `auto_invoke`. Still open; the CLI is propose-only until then.
- **Reports** (§3, §7): which rollups are worth emitting (blocked, completed, malformed) and
  in what form.
- **eng→dir upward edge** (§3.6): ✅ **specified** — R8/R9 route the `initiative:challenged`
  / `initiative:completion-requested` labels back to dir. Still open (Tier 2 / cross-repo):
  - the **feedback-label Action** (§5.4) — the `issue_comment`→label workflow in the target
    repo (not yet implemented);
  - the **routing-core support** for R8/R9 in `routing/` (add the two labels to the metadata
    + classify rules);
  - the **dir-side feedback lifecycle** — how dir acts on a challenge/completion and removes
    the label, plus a **challenge-loop cap** (specified in claude-dir-shell's SPEC; a
    separate dir-shell issue).
- **Submodule promotion** (brief §1): when the sub-repos become submodules, update the
  registry `path` resolution and remove the `.gitignore` entries. Deferred; do nothing that
  blocks it.

---

*This SPEC routes over the settled dir/res contracts (dir SPEC §4/§9; res SPEC §6.3 —
res invisibility). State/progress: `WORK_LOG.md` (same directory).*
