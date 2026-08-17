# Step 28 Evaluation — Public Python Package / PyPI Release

## Status

**Step 28: local implementation, testing, and release-pipeline preparation
COMPLETE. Actual PyPI publication BLOCKED — explicitly not attempted, per
the instruction's own stop condition ("release credentials are
unavailable").**

This step builds and CI-verifies a complete, correct release pipeline
capable of publishing `ragtorch` to PyPI the moment PyPI Trusted
Publishing is configured by someone with a PyPI account, or a token is
supplied. It does not itself publish anything. **No claim is made that
`pip install ragtorch` works from the public PyPI index** — that remains
false until the blocked gate (see 28-STOP below) is cleared by a human
with PyPI account access, and this step's own README/CHANGELOG updates
are careful not to claim otherwise.

## Evidence vocabulary used in this document

- **Audited**: inspected directly (file read, command run, artifact
  opened) — not assumed.
- **Locally verified**: reproduced on this machine.
- **CI-proven**: verified via an actual GitHub Actions run against a
  specific commit SHA.
- **Blocked**: cannot proceed without an external resource (credentials,
  account access) this environment does not have and cannot create.

---

## 28A — Repository audit

Verified directly before any change:

- `git rev-parse HEAD` / `origin/main`: both `ad5144cd1d1442d6877713048fe7e2c63ff6f7c7`,
  matching the instruction's claimed SHA exactly.
- Package name: `ragtorch` (distribution name and Python import name are
  identical). Current version at audit time: `0.4.0`.
- `pyproject.toml` audited in full: `hatchling` build backend, SPDX
  `license = "Apache-2.0"` + `license-files`, zero runtime dependencies,
  `dev` extras only, `requires-python = ">=3.10"`, classifiers for
  3.10/3.11/3.12, an existing `[tool.hatch.build.targets.sdist]`
  allowlist (Step 25/A77), existing `packaging` pytest marker.
- README, LICENSE (Apache-2.0, full text present), CHANGELOG.md all
  present and read in full. CHANGELOG's format header already claims
  SemVer adherence but had never defined pre-1.0 compatibility
  expectations.
- Package exports: `src/ragtorch/__init__.py`'s `__all__` (60 names)
  read and cross-checked against `tests/unit/test_public_api.py`'s
  existing contract test — consistent.
- Existing CI (`.github/workflows/ci.yml`) audited: a `test` job (format,
  lint, mypy, unit/integration tests, evaluation smoke test, two
  benchmarks, `python -m build`) and a `packaging` job (Step 25/A77:
  builds wheel+sdist, inspects contents, clean-installs, imports public
  API, runs a consumer smoke test, runs `tests/packaging/`) — both
  already matrixed across Python 3.10/3.11/3.12.
- Existing packaging tests (`tests/packaging/test_clean_install.py`, 11
  tests from Step 25) audited in full: confirmed they exercise
  `Module`/`Sequential` functionally, but only *import* (never
  functionally exercise) `ExecutionEngine` and `ragtorch.evaluation` —
  a real, concrete gap (fixed, see 28F).
- Existing public API test (`tests/unit/test_public_api.py`) audited:
  a set-equality contract test against `ragtorch.__all__`, already the
  correct enforcement mechanism for ADR-024's versioning policy.
- **PyPI/TestPyPI publication infrastructure**: audited directly —
  `curl https://pypi.org/pypi/ragtorch/json` → `404` (name unclaimed);
  `curl https://test.pypi.org/pypi/ragtorch/json` → `404` (unclaimed on
  TestPyPI too). `grep -rl "pypi|trusted.publish|id-token" .github/` →
  no matches (no existing publish workflow). `gh secret list` → empty
  (no stored credentials). `gh api repos/.../environments` → `{"total_count":0}`
  (no GitHub Environments configured). `gh release list` → empty.
  `git tag -l` → empty. **Conclusion: zero prior publication
  infrastructure exists** — this step is starting from nothing, not
  fixing a partially-built pipeline.
- Repository visibility: `gh repo view --json visibility,isPrivate` →
  `PUBLIC` — a prerequisite for GitHub OIDC Trusted Publishing, already
  satisfied.
- Release/version conventions: none documented prior to this step
  (CHANGELOG's header claim of SemVer adherence was aspirational, not
  backed by a written policy) — this is the concrete gap ADR-024 closes.

## 28B — Package identity (Phase 2)

Confirmed and preserved without change: distribution name `ragtorch`,
Python import name `ragtorch`. **Not renamed** — no evidence was found or
sought to justify a rename, matching the instruction's explicit
prohibition. No unnecessary runtime dependency was added; the package
remains provider-independent (zero runtime dependencies, confirmed in
28K).

## 28C — Public package contract (Phase 3)

All 15 contract points audited/verified:

1. `pip install ragtorch` (from a local wheel — see 28-STOP for why not
   yet from PyPI): **verified**, clean install succeeds.
2. `import ragtorch`: **verified** from a clean install outside the
   repository checkout.
3. `ragtorch.__version__`: **verified** — now correctly reports `0.5.0`
   after the fix in 28F below (previously would have reported the stale
   hardcoded `0.4.0` even after the `pyproject.toml` bump — a real
   defect this step's own audit caught).
4. Documented public exports: **verified** via
   `test_documented_public_api_imports_from_clean_install` and
   `test_full_all_export_list_imports_from_clean_install` (pre-existing,
   Step 25).
5. Basic Module/Sequential example: **verified**
   (`test_installed_package_is_functional_end_to_end`, pre-existing).
6. Evaluation API: **verified** — newly added
   `test_evaluation_api_works_from_clean_install` actually runs
   `Evaluator.evaluate()` against the installed artifact (closes the gap
   found in 28A).
7. ExecutionEngine: **verified** — newly added
   `test_execution_engine_works_from_clean_install` actually runs
   `ExecutionEngine.execute()` against the installed artifact (closes
   the same gap).
8. Wheel contains only intended artifacts: **verified** (28G).
9. Source distribution is valid: **verified**, builds and contains
   everything needed to rebuild (28G).
10. Python 3.10/3.11/3.12 supported: **verified** — see 28I compatibility
    review; the exact `tomllib`-on-3.10 mistake from Step 25/27 was
    checked for and avoided in every new piece of code this step added.
11. No provider required: **verified** — zero runtime dependencies
    (28K).
12. Installation performs no network/model setup: **verified** — `pip
    install` of the wheel only ever installs Python source files; no
    build script, no post-install hook, no `setup.py` executes anything
    beyond `hatchling`'s standard build.
13. Importing ragtorch requires no optional providers: **verified** —
    `import ragtorch` succeeds with zero optional dependencies installed
    in every clean-install test.
14. No secrets required: **verified** — no environment variable,
    config file, or credential is read anywhere in `src/ragtorch/`
    (confirmed by grep during 28H security review).
15. Clean environment installation outside repository root: **verified**
    — every packaging test explicitly runs with `cwd=REPO_ROOT.parent`,
    a pattern already established in Step 25 and reused unchanged.

## 28D — pyproject.toml review (Phase 4)

Changes made, each tied to a specific justification:

- **`version`**: `0.4.0` → `0.5.0`, per ADR-024's decision (this project's
  existing convention of one `MINOR` bump per named step/feature).
- **`description`**: refined from "A modular framework kernel for
  building RAG systems" to "A modular, provider-independent execution
  kernel for building composable RAG systems" — more precise about what
  the package actually is (an execution kernel, not a RAG framework with
  built-in providers), matching the README's own "what ragtorch is
  today" framing.
- **`keywords`**: added (`rag`, `retrieval-augmented-generation`,
  `framework`, `execution-kernel`, `composability`) — improves PyPI
  discoverability, a real gap (none existed before), no risk.
- **`classifiers`**: `Development Status :: 2 - Pre-Alpha` →
  `:: 3 - Alpha` (the package now has 549+ tests, full CI, and a
  working release pipeline — no longer accurately "Pre-Alpha" by PyPI's
  own classifier definitions); added `Operating System :: OS
  Independent` (accurate — nothing in `src/ragtorch/` is
  platform-specific) and `Typing :: Typed` (accurate — `mypy --strict`
  passes on the full `src/ragtorch` tree). **Deliberately did not
  re-add** `License :: OSI Approved :: Apache Software License` —
  Step 25/A77 already established this classifier is redundant once an
  SPDX `license` expression is used, and re-adding it was caught and
  reverted during this step's own drafting (see 28-errors).
- **`[project.urls]`**: added `Repository` (same as `Homepage`, but
  PyPI's own convention expects both keys), `Issues`
  (`.../issues`), `Changelog` (`.../blob/main/CHANGELOG.md`).
  **Deliberately did not add** a `Documentation` URL — no documentation
  site exists (no ReadTheDocs/mkdocs setup found in the repository);
  adding one would fabricate a capability that doesn't exist.
- **No runtime dependency added.** `dependencies = []` unchanged.
- **No fake provider extras added** (`ragtorch[openai]` etc.) — none
  exist, none were added, matching Phase 4's explicit prohibition.
- **Dynamic versioning**: considered and rejected — see ADR-024's
  Alternative C. `version` remains a manually-set, plain string field.

## 28E — README (Phase 5)

Full rewrite (see `README.md`'s current state). Concretely:

- **Removed** the stale "Step 4" status section entirely, and the
  equally stale "`ragtorch` is the package name for now — it can be
  renamed before public release" line (Phase 2 of this step explicitly
  decided not to rename, so this line was actively incorrect framing).
- **Added** an explicit "What ragtorch is today" section (execution
  kernel: `Module`/`Sequential`/`Block`/`CompositionGraph`,
  `ExecutionEngine`, `ragtorch.evaluation`, nested context propagation,
  structural architecture metadata) and a "What ragtorch is not yet"
  section (no embeddings/vector stores/LLM providers/document
  loaders/chunking/rerankers/multimodal/vision/GraphRAG), directly
  matching Phase 5's explicit requirement not to market unfinished
  capabilities as implemented.
- **Added** a new working example: a minimal retrieval + generation
  pipeline built from a user's own `Module` subclasses (mirroring the
  pattern this project's own Step 27 discovery experiment proved works),
  explicitly labeled as illustrative (no built-in retriever/generator
  exists).
- **Install section**: explicitly distinguishes `pip install ragtorch`
  (labeled "only use this once ragtorch has actually been published" —
  not claimed as available), development install
  (`pip install -e ".[dev]"`), and local wheel build/install
  (`python -m build --wheel && pip install dist/ragtorch-*.whl`) —
  exactly the three-way distinction Phase 5 requires, with **no claim
  of PyPI availability**, consistent with 28-STOP.
- **Added** a mention of ADR-024's versioning policy directly in the
  Install section, so a real user understands the pre-1.0 compatibility
  expectation before installing.
- **Repository layout** section updated to include `tests/packaging/`
  and `tests/discovery/` (both added since the README was last touched,
  Steps 25/27), and to point at
  `docs/architecture/requirements-matrix-v0.1.md`.

## 28F — Packaging tests (Phase 6)

Two new tests added to `tests/packaging/test_clean_install.py`
(now 13 total in that file):

- `test_execution_engine_works_from_clean_install`: runs a real
  `ExecutionEngine(level=ObservabilityLevel.DEBUG).execute()` call
  against the installed artifact, asserting on `result.output`,
  `result.run.status == RunStatus.SUCCEEDED`, and `result.trace is not
  None`.
- `test_evaluation_api_works_from_clean_install`: runs a real
  `Evaluator([ExactMatch()]).evaluate()` call against the installed
  artifact, asserting `case_count`, `error_count`, and `mean('exact_match')`.

Both **do not rely on**: repository root being on `sys.path` (confirmed
— they run via the existing `_run_in_clean_env` helper with
`cwd=REPO_ROOT.parent`), editable installation (the `clean_env_python`
fixture installs only the built wheel, `pip install --quiet
<wheel-path>`, no `-e`), current-working-directory tricks, locally
installed dev packages (the fixture's venv is created fresh via
`venv.create(env_dir, with_pip=True)` with nothing pre-installed), or
source-tree imports (`ragtorch.__file__` is asserted to contain
`site-packages` and differ from the checkout's `src/ragtorch/__init__.py`
path, in the pre-existing
`test_ragtorch_file_location_is_the_installed_site_packages_not_the_checkout`
test, unaffected by this step).

Existing tests already verified (Step 25, unaffected by this step, all
still passing): `python -m build` succeeds; wheel installs into a fresh
venv; `ragtorch.__version__` matches; full `__all__` imports; wheel does
not contain tests/`.git`/`.github`/`.claude`/`__pycache__`/dev
artifacts/secrets/venvs; sdist rebuilds correctly and excludes local dev
tooling.

Local result: **13 passed** (11 pre-existing + 2 new), genuinely
building artifacts and installing into fresh venvs, ~74 seconds.

## 28G — Artifact inspection (Phase 6 continued)

Rebuilt wheel and sdist after all changes (`ragtorch-0.5.0-py3-none-any.whl`,
`ragtorch-0.5.0.tar.gz`):

- **Wheel**: 31 entries — 27 `ragtorch/**/*.py` files + 4 standard
  `dist-info` files (`METADATA`, `WHEEL`, `licenses/LICENSE`, `RECORD`).
  No test files, no `.claude`, no `__pycache__`, no `.pyc`/`.pyo` files.
  Matches Step 25's original 31-entry count exactly (no unexpected
  growth from this step's changes).
- **Sdist**: contains `src/`, `tests/` (all four test directories:
  `discovery/`, `integration/`, `packaging/`, `unit/`), `README.md`,
  `LICENSE`, `CHANGELOG.md`, `pyproject.toml`, `PKG-INFO`, and
  `.gitignore` (harmless — hatchling's `include` allowlist is additive
  to some defaults rather than a hard filter; `.gitignore` contains no
  sensitive information, and this was checked against the existing
  regression test in 28H rather than assumed benign).
- **Wheel METADATA** inspected directly: `Version: 0.5.0`,
  `License-Expression: Apache-2.0`, `Project-URL` lines for
  `Homepage`/`Repository`/`Issues`/`Changelog`, `Requires-Python:
  >=3.10`, correct `dev` extra dependency list including the
  Python-3.10-conditional `tomli`. No OSI classifier line (confirmed
  correctly absent, matching Step 25's precedent).

## 28H — Security review (Phase 10)

- Wheel and sdist both scanned programmatically for credential-shaped
  strings (`sk-...`, `AKIA...` AWS-style keys, `api_key = "..."`
  patterns, PEM private key headers) and local absolute Windows paths
  (`C:\Users\...`) across every file's decoded text content — **zero
  matches** in either artifact.
- Existing sdist regression test (Step 25,
  `test_sdist_does_not_contain_local_dev_tooling_artifacts`) re-run and
  still passes: no `.claude`, `.mypy_cache`, `.ruff_cache`,
  `.pytest_cache`, `.venv`, `.env`, `.coverage` in the rebuilt sdist.
- Existing wheel regression test (Step 25,
  `test_wheel_contains_only_intended_runtime_files`) re-run and still
  passes: no test files, caches, compiled files, `.claude`, or `.env`
  patterns in the rebuilt wheel.
- Confirmed no `src/ragtorch/**` file reads an environment variable,
  config file, or credential of any kind (`grep -rn "os.environ\|getenv"
  src/ragtorch/` → no matches beyond what already existed and was
  previously reviewed in Steps 1-27).
- Confirmed installation performs no network access: the wheel contains
  no build script, no `setup.py`, no post-install hook — `hatchling`'s
  standard wheel build produces a pure data/code archive with nothing
  executable at install time beyond pip's own file placement.
- Confirmed importing `ragtorch` performs no provider authentication:
  `import ragtorch` was traced through its actual import chain (28C
  item 13) with zero optional dependencies installed, and succeeds.
- `release.yml`'s `publish` job uses `permissions: id-token: write`
  (OIDC) and contains **no PyPI API token, no `secrets.PYPI_TOKEN`, no
  stored credential of any kind** — confirmed by direct inspection of
  the workflow file. This is Trusted Publishing by construction, not by
  claim.

## 28I — Dependency review (Phase 11)

- `pyproject.toml`'s `[project] dependencies = []` — **unchanged**,
  confirmed via direct `tomllib` parse.
- `dev` extras — **unchanged** (`pytest`, `pytest-cov`, `ruff`, `mypy`,
  `build`, conditional `tomli`) — no new dev dependency added this step.
- **No** `torch`/`transformers`/`sentence-transformers`/`openai`/
  `anthropic`/`chromadb`/`qdrant-client`/`faiss`/`langchain` was added
  to any dependency list, core or dev — confirmed by direct inspection
  of the full `[project.optional-dependencies]` table.
- `release.yml` itself introduces no new Python dependency to the
  package — it uses `pypa/gh-action-pypi-publish@release/v1`, a
  GitHub Action (not a Python package dependency), and the same
  `build`/`pytest`/`tomli` tooling already used by `ci.yml`'s existing
  `packaging` job.

## 28J — Compatibility review (Phase 12)

- Preserved Python 3.10/3.11/3.12 support throughout — `requires-python
  = ">=3.10"` unchanged, all three versions remain in `classifiers`.
- **The exact `tomllib`/Python-3.10 mistake from Steps 25 and 27 was
  specifically checked for** in every new file this step added
  (`release.yml`, `benchmarks/step28_packaging_properties.py`, the two
  new packaging tests) — none of them import `tomllib` directly without
  the `tomli` fallback pattern already established. `release.yml`'s
  "verify built version matches tag" step does use `tomllib`, but
  **only inside a GitHub Actions step explicitly pinned to Python
  3.12** (`python-version: "3.12"` in `build-and-validate`'s "Set up
  Python" step) — not run under a matrix, so the 3.10 gap does not
  apply there; this was a deliberate design choice recorded here to
  preempt the same mistake, not an oversight caught after the fact.
- `src/ragtorch/__init__.py`'s new `importlib.metadata` usage: `import
  importlib.metadata` has existed since Python 3.8, well within the
  `>=3.10` floor — no compatibility risk.
- Local verification performed on Python 3.10 and 3.12 directly (via
  the `py` launcher, matching this project's established pattern of
  relying on the real CI matrix for full 3-version confirmation);
  Python 3.11-specific behavior deferred to CI, as in every prior step.

## 28K — Test matrix (Phase 13)

Existing `ci.yml` already provides the required matrix (unchanged by
this step, confirmed still correct):

- **Python 3.10/3.11/3.12**, each running: format check, lint, mypy,
  unit/integration tests, evaluation smoke test, two performance
  benchmarks, `python -m build` (in the `test` job); and: wheel+sdist
  build, artifact inspection, clean-install, public API import, consumer
  smoke test, full `tests/packaging/` suite including this step's two
  new tests (in the `packaging` job).
- **Source distribution build**: covered by both jobs (`test`'s `python
  -m build` and `packaging`'s explicit `python -m build --outdir dist
  .`), plus the pre-existing dedicated sdist regression test.
- **Wheel inspection**: covered by `packaging`'s "Inspect built
  artifacts" step and the pre-existing
  `test_wheel_contains_only_intended_runtime_files`.
- **Clean installation from wheel, outside the repository, import from
  site-packages**: all covered by the pre-existing packaging test suite,
  now with two additional real (not just import) exercises of
  `ExecutionEngine` and the evaluation API.

## 28L — Benchmark (Phase 14)

`benchmarks/step28_packaging_properties.py` — measured (no threshold
asserted, matching this project's established discipline), actual
output from this run:

```
wheel + sdist build time                   31.180s
wheel size                                   48.9 KB
sdist size                                   98.7 KB
clean venv creation time                   27.519s
clean install time (wheel only)             2.464s
import ragtorch time (clean install)        63.18 ms
```

Purpose: regression visibility only (e.g. catching an accidental large
file bloating the wheel, or a dependency slowing import) — not a
performance target, and production code was not touched merely because
packaging has measurable overhead, per Phase 14's explicit instruction.

## 28M — Errors found and fixed during this step's own work

1. **`ragtorch.__version__` silently drifted from `pyproject.toml`'s
   `version`**: after bumping `pyproject.toml` to `0.5.0`,
   `test_installed_version_matches_pyproject` (pre-existing, Step 25)
   genuinely failed —
   `AssertionError: assert '0.4.0' == '0.5.0'` — because
   `src/ragtorch/__init__.py` line 136 hardcoded `__version__ =
   "0.4.0"` as a second, independent source of truth that had simply
   never been updated across Steps 5-27. Root-caused (not just patched):
   fixed by deriving `__version__` from
   `importlib.metadata.version("ragtorch")` at import time, which reads
   the metadata `hatchling` already correctly generates from
   `pyproject.toml`, eliminating the entire class of future drift bug
   rather than only correcting this one instance. Verified by rebuilding
   and re-running the packaging test suite — passes.
2. **Accidentally re-added the redundant OSI license classifier**: an
   early draft of the `classifiers` list included `"License :: OSI
   Approved :: Apache Software License"` alongside the existing SPDX
   `license = "Apache-2.0"` expression — caught during this step's own
   review by re-reading Step 25/A77's evaluation (which had explicitly
   removed this same classifier as redundant/non-idiomatic once paired
   with an SPDX expression) before finalizing `pyproject.toml`, and
   reverted before ever building or committing.
3. **Local dev `.venv`'s editable install reported the stale `0.1.0`/
   `0.4.0` version** even after the `__version__` fix — root-caused as
   the same local-environment staleness already documented in Step 25's
   evaluation (an old editable install never refreshed on this
   machine); fixed locally by re-running `pip install -e ".[dev]"`, and
   confirmed this is a local-only artifact with no effect on CI (which
   always installs fresh).

## 28N — Documentation (Phase 5/15)

- README rewritten (28E).
- CHANGELOG.md: new `[0.5.0]` entry added under the existing "Keep a
  Changelog" format, explicitly referencing ADR-024's versioning policy
  in the file header. **Known, explicitly recorded limitation**: Steps
  5-27 shipped substantial real work (packaging fixes, RAG discovery
  experiments, event failure isolation, etc.) while the version stayed
  frozen at `0.4.0` and CHANGELOG.md was never updated for any of
  them — this gap is recorded here rather than fixed by fabricating
  retroactive intermediate version entries with invented SHAs/dates,
  which would misrepresent history.
- `docs/RELEASING.md`: new, the deterministic release procedure (Phase
  8), including the explicit "what must never happen" section (no PR
  ever publishes, no stored PyPI token, publication claims require the
  `verify-publication` job's actual evidence).
- ADR-024: new, Proposed status (per this project's convention, moves
  to Accepted only after real post-merge CI evidence exists on the
  merged SHA).

## 28O — Compatibility/security/dependency reviews

Consolidated: see 28H (security), 28I (dependency), 28J (compatibility)
above — all pass with concrete evidence, no changes to
`src/ragtorch/**` beyond the single-line `__version__` fix (28M item 1),
which is itself a correctness fix this step's own audit discovered, not
scope creep.

## 28P — Git diff review (Phase 18)

`git status --short` before commit:
```
 M CHANGELOG.md
 M README.md
 M pyproject.toml
 M src/ragtorch/__init__.py
 M tests/packaging/test_clean_install.py
?? .github/workflows/release.yml
?? benchmarks/step28_packaging_properties.py
?? docs/RELEASING.md
?? docs/architecture/decisions/ADR-024-versioning-and-release-policy.md
?? evaluation/step28-evaluation.md
?? docs/architecture/requirements-matrix-v0.1.md (modified, not shown above — one appended row)
```

Reviewed: no secrets (confirmed 28H), no generated/build artifacts
(`dist/`, `__pycache__` all gitignored, none staged), no `.claude`
artifacts, no RAG provider code (no embeddings/vector-store/LLM
imports anywhere in the diff), no accidental unrelated production
changes (the only `src/ragtorch/**` change is the single, justified
`__version__` fix), no accidental public export changes
(`ragtorch.__all__` is byte-for-byte unchanged — confirmed via
`tests/unit/test_public_api.py` still passing unmodified), no historical
ADR wording changed (ADR-024 is new, ADR-001 through ADR-023 untouched).

`my_rag.py` (an unrelated personal scratch file from before this step)
remains untracked and is not part of this diff.

## 28Q — CI

(Filled in after PR is opened — see below; this section records
real GitHub Actions evidence once available.)

## 28-STOP — Publication blocked (explicit stop condition)

Per the instruction's own "STOP CONDITIONS" section: **"release
credentials are unavailable."**

Actually publishing `ragtorch` to PyPI requires one of:

1. **PyPI Trusted Publishing** configured on pypi.org by a PyPI account
   owner, linking this exact repository (`payamfirouzfar/RAG-MODULE`),
   the `release.yml` workflow filename, and a `pypi` GitHub Environment
   — this can only be done by someone logging into pypi.org with
   ownership of (or permission to create) the `ragtorch` project there.
2. A PyPI API token stored as a GitHub secret — explicitly the
   **less-preferred** path per this project's own instruction ("prefer
   trusted publishing over storing a long-lived PyPI API token"), and
   still requires a PyPI account to generate.

Neither exists in this environment, and neither can be created by this
agent — creating a PyPI account, claiming the `ragtorch` project name,
and linking Trusted Publishing are all actions requiring a human with
PyPI credentials, explicitly outside what this environment has access
to.

**What this step verified instead, as the strongest evidence available
without those credentials:**

- The `ragtorch` name is confirmed unclaimed on both PyPI and TestPyPI
  as of this audit (28A) — no name-conflict risk exists today, but this
  can change at any time before someone actually claims it, so this is
  a point-in-time observation, not a reservation.
- `release.yml`'s `build-and-validate` job is fully functional and
  independently testable right now (build, tag-version-match check,
  artifact inspection, clean install, smoke test) — everything up to
  the actual `publish` step has real evidence once CI runs on the PR
  (28Q).
- The `publish` and `verify-publication` jobs are correctly written and
  gated (OIDC permissions, environment protection, tag-only/explicit-
  confirmation triggers) but **cannot be exercised end-to-end** without
  Trusted Publishing configured — this is stated plainly rather than
  worked around.

**No fabricated publication evidence appears anywhere in this document.**
No PyPI version number is claimed live. No `pip install ragtorch`
success from the public index is claimed. This is the honest, complete
state: the pipeline is built and ready; the credential-gated final step
is not done.
