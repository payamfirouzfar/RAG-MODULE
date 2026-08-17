# ADR-024: Versioning and Release Policy

## Status

Proposed — will be moved to Accepted only after real GitHub Actions
post-merge CI confirms this policy's supporting infrastructure (packaging
tests, release workflow) on the actual merged `main` SHA, per this
project's standing rule.

## Context

`ragtorch` is about to become publicly installable (`pip install
ragtorch`, Step 28). Until now, versioning has been informal: five
versions (0.1.0 through 0.4.0) were bumped in `pyproject.toml` at
milestone boundaries, documented in `CHANGELOG.md`, with no written policy
for what a version bump means or what compatibility a user can expect
between versions.

`CHANGELOG.md`'s own header already states the project "adheres to
Semantic Versioning" — but nothing has defined what that means
concretely for a project that is explicitly pre-1.0 (`Development Status
:: 2 - Pre-Alpha` in `pyproject.toml`'s classifiers) and has, in practice,
made several backward-incompatible changes across 0.x versions already
(e.g. Step 20/A72's `ListenerDeliveryError` propagation was an explicit,
named breaking change to `EventBus.publish()`/`EventScope.publish()`,
documented as such but shipped as a 0.x → 0.x bump, not a major-version
bump — because no major version above 0 exists yet to signal it with).

Once real external users can `pip install ragtorch`, an undocumented
versioning policy stops being a private inconvenience and starts being a
real compatibility risk for anyone who pins a version range.

## Decision

Adopt Semantic Versioning (SemVer 2.0.0) with the standard pre-1.0
qualification it already defines, made explicit here rather than left
implicit:

- **While `MAJOR` is `0`** (i.e., every `0.x.y` release, including all
  releases to date and the near-term future): the public API is **not**
  guaranteed stable between `MINOR` version bumps. A `0.x` → `0.(x+1)`
  bump may include breaking changes to any part of the public API
  (`ragtorch.__all__`), following SemVer's own explicit allowance for
  this during initial development. `PATCH` bumps (`0.x.y` → `0.x.(y+1)`)
  are reserved for backward-compatible fixes only — no public API
  removal or signature change.
- **Once `MAJOR` reaches `1`** (`1.0.0`): standard SemVer applies in
  full — `MAJOR` bumps may break the public API, `MINOR` bumps add
  functionality in a backward-compatible way, `PATCH` bumps are
  backward-compatible fixes only.
- The **public API surface** that this policy governs is exactly
  `ragtorch.__all__` (currently 60 names, contract-tested by
  `tests/unit/test_public_api.py`) — not every symbol reachable via
  `ragtorch.core.*` submodule imports, which remain implementation
  details subject to change without a version-policy implication, per
  this project's existing precedent (e.g. `ragtorch.core.module`'s
  private `_GraphBackedRAGModule` adapter, ADR-021, was never exported
  and is not part of this contract).
- **What justifies 1.0.0**: this ADR does not set a date or a feature
  checklist for reaching 1.0.0 — doing so now would be exactly the kind
  of speculative commitment this project's own established discipline
  (A11, A61, A76, A78, A79) has consistently rejected making without
  real evidence. 1.0.0 is reserved for whenever the project has real
  external consumer evidence (Step 27's own conclusion: still absent as
  of this ADR) that the current public API shape is stable enough to
  commit to not breaking casually.
- **Every version bump must update `CHANGELOG.md`** under the existing
  "Keep a Changelog" format already in use, with an explicit note when a
  release includes a breaking change to `ragtorch.__all__` (matching the
  precedent already set for 0.5.0-equivalent changes like A72's listener
  failure isolation, A77's packaging fixes, etc., even though those were
  not retroactively logged under this policy).
- **`pyproject.toml`'s `version` field remains the single source of
  truth**, set manually (no dynamic versioning from git tags or
  VCS-derived version schemes) — this project already has a working,
  simple, single-source-of-truth version string, and introducing dynamic
  versioning now would add release-process complexity with no concrete
  problem it solves (Phase 4's own instruction: "If dynamic versioning
  would create unnecessary complexity, keep the current simple
  versioning approach").

### Step 28's own version choice

Step 28 (this ADR's companion step) adds packaging/release infrastructure
only — no public API change, no new runtime dependency, no behavior
change to any existing `Module`/`Sequential`/`ExecutionEngine`/evaluation
code. Per this policy, that qualifies as a `PATCH`-eligible change in
spirit (backward-compatible, no API removal), but the project's own
existing convention (see `CHANGELOG.md`'s prior entries, e.g. 0.3.0 → 0.4.0
for Step 4, itself an additive, non-breaking change) has consistently
used `MINOR` bumps for each named step/milestone rather than `PATCH`, to
keep the version number legible against this project's own step-numbered
history. This ADR keeps that existing convention rather than introducing
a new one: Step 28 ships as **0.5.0**.

## Alternatives considered

**A. Freeze at 0.4.0, don't bump for packaging-only work.** Rejected —
the first-ever public PyPI release is exactly the kind of event a user
needs to be able to identify by version number; shipping the actual
first public release under an already-existing internal version number
would make "which version was first published" undiscoverable from
`CHANGELOG.md`/git tags alone.

**B. Jump straight to 1.0.0 for the first public release.** Rejected —
explicitly forbidden by this ADR's own reasoning above: 1.0.0 signals API
stability commitment this project has no real-consumer evidence to
support yet (Step 27's own conclusion). Jumping to 1.0.0 merely because a
release is "public" would conflate "installable" with "stable," which
are different claims.

**C. Dynamic/calendar versioning (e.g. `2026.8.0`).** Rejected — no
problem exists that calendar versioning would solve here; it would
discard the legible step-numbered SemVer-minor convention this project's
CHANGELOG already has five versions of history under, for no concrete
benefit.

**D. Use `PATCH` bump (0.4.1) for this step since it's packaging-only,
not a feature.** Rejected — inconsistent with this project's own
established convention of one `MINOR` bump per named step (see Decision
section above); would create two different versioning conventions
running simultaneously with no clear rule for which applies when.

## Consequences

- Every future step that changes `ragtorch.__all__` must record whether
  the change is additive or breaking in `CHANGELOG.md`, and the version
  bump must reflect this ADR's rules.
- This project makes **no promise** that `pip install ragtorch==0.4.*`
  and `pip install ragtorch==0.5.*` are interchangeable — real users
  pinning a version range must pin an exact `0.x.y`, not a `0.x.*`
  range, until 1.0.0.
- `tests/unit/test_public_api.py`'s existing export-set contract test
  becomes this policy's enforcement mechanism: any PR that changes
  `ragtorch.__all__` will fail that test until updated, which is the
  concrete trigger for "does this version bump need a breaking-change
  note in CHANGELOG.md."
