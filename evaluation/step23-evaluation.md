# Step 23 Evaluation — CompositionGraph Incremental Validation Audit (A61)

Date: 2026-08-17 (23A-23F, local) — pending CI/merge

## Status

**Overall status: IN PROGRESS.**

This step's central result is **Outcome A**: no real workload
demonstrates that `CompositionGraph`'s full-revalidation-per-update
cost matters. No ADR-024, no production code change. The deliverable
is a workload model built from repository evidence, a dedicated
benchmark, a design-space comparison, and precise documentation.
Remaining: push, PR, CI, merge, post-merge CI, final closure.

## Evidence vocabulary

Frozen vocabulary reused verbatim from Steps 18-22.

## Phase 1 — Repository audit

Confirmed `main` at `fa6f56a5bfa1208c055d864080d6415e2529ceea` (Step 22
final closure) via `git log`/`git rev-parse HEAD`. 522 tests at start.
Python support: 3.10/3.11/3.12 (`.github/workflows/ci.yml`,
`pyproject.toml`).

**Key structural finding, the central fact of this audit:**
`grep -Rln "add_node\|add_connection\|remove_node\|remove_connection" src/ragtorch/ --include="*.py"`
returns **only `composition.py` itself** — zero other production file
calls any of `CompositionGraph`'s four functional-update methods.
`Block`, `ExecutionPlan`'s `plan()`, and `RAGModule.from_graph` all
consume a `CompositionGraph` exclusively via **construction**
(`CompositionGraph(nodes=..., connections=...)`, confirmed by
`grep -Rln "CompositionGraph(" src/ragtorch/` returning zero matches
outside `composition.py` itself — every real consumer receives an
already-built graph as a parameter and never mutates it).

Test-only usage of the four methods
(`grep -Rln ... tests/` → `test_composition.py`, `test_execution_plan.py`)
is exclusively small-scale (2-4 nodes) correctness verification — no
test exercises repeated/chained mutation at any meaningful scale.

Zero GitHub issues exist (`gh issue list --repo payamfirouzfar/RAG-MODULE --state all` —
empty), open or closed — no external signal that this is a real
problem for any user.

ADR-016 and A61 read in full; A61's exact current text: *"functional
updates re-validate the full graph rather than incrementally verifying
only the delta — see `evaluation/step12-evaluation.md` Limitations,"*
with Step 12's own evaluation explicitly framing this as *"an explicit,
accepted tradeoff for correctness simplicity over marginal
performance, not silently absorbed"* and naming incremental validation
as *"additive, not a contract change"* if ever pursued — consistent
with this audit's own conclusion, not contradicted by it.

## Phase 2 — Workload model

Built from repository evidence, not invented:

| Workload | Evidence for this pattern being real | Conclusion |
|---|---|---|
| A. Small static graph, construct once | **Confirmed as the only pattern any real consumer uses** (Phase 1) | Dominant, real |
| B. Build-time chained functional construction | No real consumer does this — only small (2-4 node) test fixtures | **No real-world evidence** — constructed as a synthetic worst case for this audit's own benchmark, not because a caller does this |
| C. Repeated branching from one base graph | No real consumer does this | No evidence |
| D. Large graph (10/100/1,000/10,000 nodes) | Real — matches Step 12's own established benchmark scales, and `ExecutionPlan`'s `plan()` (Step 13) uses the same scales for its own, unrelated derivation cost | Real, but for **construction**, not repeated mutation |
| E. Connection-heavy graph | Real shape (higher fan-out than a linear chain), constructed for this audit since no prior benchmark measured it | Plausible future graph shape, still construct-once |
| F. Repeated updates to an already-large graph | No real consumer does this | No evidence — constructed as a synthetic worst case |

**Explicit conclusion**: no repository evidence supports Workload B, C,
or F as real usage patterns. They are included in this audit's
benchmark anyway, as synthetic worst-case characterizations, precisely
so this document does not have to guess at their cost later if the
question ever recurs.

## Phase 3 — Baseline benchmark

`benchmarks/step23_composition_graph_update_audit.py`, six workloads:

```
Workload B -- build-time functional construction (chained, from empty):
  chained add_node to    10 nodes: p50=    35.350us
  chained add_node to   100 nodes: p50=  1356.150us
  chained add_node to  1000 nodes: p50=133533.450us

Workload C -- repeated branching (one base, many single-update derivations):
  single add_node() branching off a 100-node base: p50=97.300us

Workload D -- large graph construction (re-run of Step 12's scaling check):
  construction at     10 nodes: p50=       9.900us
  construction at    100 nodes: p50=      94.400us
  construction at   1000 nodes: p50=    1113.650us
  construction at  10000 nodes: p50=   16340.600us

Workload E -- connection-heavy graph (fan-out, not just linear chain):
  100 nodes, 50 edges from n0: p50=193.650us
  100 nodes, 99 edges from n0: p50=320.450us

Workload F -- repeated updates against an already-large (1,000-node) graph:
  single add_node() on a 1,000-node graph: p50=1129.050us

python=3.12.0
```

**Interpretation:**

- **Workload D** (real, construct-once) scales roughly linearly:
  9.9µs → 94.4µs → 1,113.7µs → 16,340.6µs as node count grows
  10 → 100 → 1,000 → 10,000 (each 10x growth in size costs roughly
  9-15x in time) — consistent with Step 12's own original finding, no
  quadratic blowup at realistic construct-once scale.
- **Workload F** (synthetic worst case, single update on an
  already-large graph) costs ~1,129µs, matching Workload D's
  1,000-node *construction* cost almost exactly — directly confirms
  "update = full rebuild at current size" is the precise, correct
  characterization, not merely a plausible-sounding claim.
- **Workload B** (synthetic worst case, chained construction) is the
  *only* place the cost compounds meaningfully: 35µs → 1,356µs →
  133,533µs as final size grows 10 → 100 → 1,000, an
  O(n²)-shaped total cost (each of the n `add_node()` calls does
  O(current size) work, summing to O(n²)). At 1,000 nodes this is
  ~133.5 milliseconds *total* for the full chain — a real number, but
  one **no actual caller in this codebase ever pays**, since no
  consumer builds graphs this way (Phase 1).
- **Comparable, already-accepted cost elsewhere**: `ExecutionPlan`'s
  `plan()` derivation costs ~855µs at 1,000 nodes (Step 13's own
  benchmark) and is **re-derived on every single `Block.forward()`
  call** with no caching (ADR-020 Q11, explicitly deferred pending
  evidence) — this project already tolerates a comparable-magnitude,
  per-call cost at the same scale, for the identical "no evidence it
  matters yet" reasoning this audit reaches independently.
- **Note on absolute figures vs. Step 12's historical numbers**: this
  run's 10/100/1,000-node construction figures (9.9µs/94.4µs/1,113.7µs)
  are noticeably faster than Step 12's originally recorded figures
  (39.3µs/~380µs, per `evaluation/step12-evaluation.md`) on what is
  presumably different hardware — the implementation is unchanged
  (confirmed via `git log -- src/ragtorch/core/composition.py` showing
  no commits since Step 12), so this is recorded as environment
  variance, not a performance regression or improvement to claim
  credit for.

## Phase 4 — Design space

Six alternatives compared against 18 criteria (correctness,
immutability, deterministic iteration, API compatibility, failure
atomicity, graph equality/hash semantics, memory usage, invalid-state
exposure, concurrency, serialization, future async, cache-invalidation
complexity, debugging complexity, testability, maintainability,
migration cost, provider independence, dependency impact):

| Option | Verdict |
|---|---|
| A. Keep full validation as-is | **Only evidence-justified option** — zero correctness risk, zero new complexity, already correct and tested |
| B. Incremental validation via derived indexes | Not justified — would require a full parallel incremental implementation of all 9 validation passes to keep in sync forever; incremental cycle detection specifically is a known-hard problem (see Phase 5) |
| C. Private internal validated-state/cache | Not justified — solves nothing: `CompositionGraph` instances are validated exactly once at construction (`__post_init__`), never re-validated after — there is no repeated validation of the *same* instance to cache |
| D. Internal mutable builder + immutable public snapshots | Not justified — no evidence any caller wants a builder API; would only help Workload B, which no real consumer exercises |
| E. Copy-on-write/persistent data structure | Not justified — likely requires a new dependency or substantial custom implementation; same "no dependency without extraordinary evidence" bar this audit itself must apply, not met |
| F. Cached validation results | Not justified — same reasoning as C |

## Phase 5 — Adversarial review

Ran the 20-item hazard checklist against Option B specifically (the
most plausible "if we did this" candidate), even though the evidence
already points to Outcome A:

- **Incremental cycle-detection bypasses**: the single hardest problem
  identified. Incremental cycle detection on edge *addition* is
  tractable (check whether the new edge creates a path back to its
  source), but incremental detection on node/edge *removal* generally
  requires re-deriving reachability from scratch anyway — defeating
  much of the purpose of "incremental."
- **Stale validation indexes**: real risk — any missed mutation path
  (including a future new method) would silently produce stale
  index state, a correctness class the current plain-tuple design
  cannot exhibit at all.
- **Branch/version contamination**: if any index were shared via a
  copy-on-write optimization, two derived graphs could accidentally
  alias mutable index state — a new correctness risk class this
  project's current fully-immutable-tuple design avoids entirely.
- Every other item on the 20-point checklist (duplicate-node bypasses,
  dangling-connection bypasses, fan-in bypasses, equality/hash
  inconsistencies, mutation leaks, thread-safety assumptions,
  serialization exposure, etc.) reduces to the same root concern:
  index synchronization correctness is unproven and would introduce
  real risk into a component that is currently simple and fully
  correct.

**Conclusion**: even setting aside the complete absence of workload
evidence, the *engineering cost* of doing this correctly is
substantial and would trade a simple, fully-correct component for a
more complex one with new correctness risk classes that do not exist
today.

## Phase 6 — Decision: OUTCOME A

**No change justified.** No production code change. No ADR-024. A61
remains explicitly **Deferred**, re-confirmed rather than resolved,
with new evidence recorded for *why* it remains the right call:

1. Zero real consumers ever call the four functional-update methods.
2. Zero GitHub issues identify this as a problem.
3. The only workload where the cost compounds meaningfully (chained
   construction, O(n²)-shaped) has no real caller anywhere in this
   codebase.
4. A comparable-magnitude cost (`plan()` derivation) is already
   tolerated elsewhere in this same codebase without optimization, for
   the identical reasoning.
5. The engineering cost of a correct incremental implementation
   (specifically: incremental cycle detection) is substantial and
   would introduce new correctness risk classes.

## Compatibility review

No public API change: `CompositionGraph`, `GraphNode`, `add_node`,
`add_connection`, `remove_node`, `remove_connection` all unchanged.
Python 3.10/3.11/3.12 unaffected (no production code touched). No new
dependency — confirmed via `git diff` against every manifest file
(empty). `Block`, `ExecutionPlan`, `RAGModule`, `Component`,
`Connection`, `Module`, `EventBus`/`EventScope` — all unaffected.

## Security review

No production code change means no new security surface. Confirmed
this audit's own new benchmark code does not execute components during
measurement (`FakeComponent.__call__` is never invoked — only
`GraphNode`/`Connection`/`CompositionGraph` construction is measured),
matching `CompositionGraph`'s own existing "never executes a
component" invariant.

## Dependency review

`git diff` against every dependency manifest — empty. No dependency
changes, and none were proposed (Option E, the only alternative that
might have required one, was rejected in Phase 4 without needing to
reach that question).

## Diff review

```
git status --short (pre-commit):
?? benchmarks/step23_composition_graph_update_audit.py
?? evaluation/step23-evaluation.md
```

`src/ragtorch/core/composition.py` and every other production file —
confirmed unmodified. This is the expected, correct footprint for a
genuine Outcome-A step: evidence and documentation only, zero
production code.

## Closure

Pending: push, PR, CI (3.10/3.11/3.12), merge, post-merge CI
verification, final closure record. A61's evidence column will be
updated (not rewritten — append-only, following the same convention
Steps 21/22 established for `EVT-RACE-001`/`EVT-REENTRANT-001`) with a
pointer to this audit once CI evidence exists. Whether a new
requirements-matrix row (A75) is warranted, versus updating A61's
existing evidence in place, will be decided during closure by checking
which convention the project's own history actually uses for an
audit that reconfirms rather than newly fulfills a named limitation.
