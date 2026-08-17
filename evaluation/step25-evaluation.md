# Step 25 Evaluation — ragtorch Package / Clean-Install Readiness

## Status

**Step 25: COMPLETE.** Local implementation, PR CI, merge, and post-merge CI on `main` are all evidence-backed (see Phase 10).

Scope, per the Step 25 instruction: packaging/release infrastructure only. No LLM,
embedding, vector store, multimodal RAG, Graph RAG, provider adapter, or
orchestration code was implemented or is present in this step's diff.

## Evidence vocabulary used in this document

- **Audited**: inspected directly (file read, command run, artifact opened) — not assumed.
- **Locally verified**: reproduced on this machine (Windows, Python 3.10 and 3.12 via
  the `py` launcher; Python 3.11 not available locally — deferred to CI matrix per this
  project's established pattern).
- **CI-proven**: verified via an actual GitHub Actions run against a specific commit SHA,
  inspected via `gh run view`, not assumed from a green badge.
- **Fixed**: a concrete defect found in the audit and corrected, then re-verified by
  rebuilding/re-inspecting the artifact.

## Phase 1 — Repository audit

Audited before any change: `pyproject.toml`, `src/ragtorch/` package layout,
`src/ragtorch/__init__.py`'s `__all__`, `README.md`, `.github/workflows/ci.yml`,
`LICENSE`, `.gitignore`, and the existing dev `.venv`'s installed state.

Findings:

- `python -m build` already succeeded before any Step 25 change (confirmed by running it
  directly). Packaging was **not** broken in the sense of "does not build" — consistent
  with the instruction's explicit warning not to assume brokenness.
- The wheel already contained only `ragtorch/` runtime `.py` files — no test files, no
  caches, at audit time.
- The **sdist** contained `.claude/scheduled_tasks.lock`, a local development artifact.
  Root cause: `.claude/` was excluded only via this machine's personal
  `.git/info/exclude`, never the repository's own tracked `.gitignore`. `hatchling`'s
  default sdist file selection follows the repo's own `.gitignore`, so the artifact
  leaked into any sdist built from a clean clone (i.e., in CI, not just locally).
- `pyproject.toml`'s `[project.urls] Homepage` pointed at a nonexistent placeholder
  (`https://github.com/ragtorch/ragtorch`) instead of the real repository
  (`https://github.com/payamfirouzfar/RAG-MODULE`).
- `license = { file = "LICENSE" }` embeds the full Apache-2.0 license text into the
  wheel's METADATA `License:` field (confirmed: ~18KB of metadata bloat), which is
  non-idiomatic and deprecated when paired with an OSI `classifiers` entry.
- `.github/workflows/ci.yml` ran `python -m build` at the end of the `test` job but never
  installed the built artifact into a clean environment, never imported `ragtorch` from
  outside the source checkout, and never ran any test against the installed wheel — CI
  exercised only the editable, in-repo install (`pip install -e ".[dev]"`).
  There was no clean-install consumer smoke test anywhere in the repository.
  `dev` optional-dependencies already correctly excluded from any runtime path (runtime
  `dependencies = []`).
- README's `## Install (development)` section did not distinguish "not yet on PyPI" from
  "install from source" and gave no guidance for testing a real built wheel.
- The dev `.venv`'s editable install reported version `0.1.0` against `pyproject.toml`'s
  authoritative `0.4.0` — audited and determined to be **local development-environment
  staleness only** (an old editable install never refreshed), not a packaging defect; CI
  always installs fresh, so this does not affect CI or artifact correctness. Deliberately
  left unfixed as out of scope.
- README's `## Status` section (referencing "Step 4") and general documentation currency
  were audited and found stale, but are explicitly out of scope for this step per the
  instruction ("packaging/release infrastructure only" — not general documentation
  currency).

## Phase 2 — Fixes (concrete gaps only)

1. **`.gitignore`**: added `.claude/` (repo-tracked fix for the sdist leak).
2. **`pyproject.toml`**:
   - Added `[tool.hatch.build.targets.sdist] include = [...]` explicit allowlist
     (`/src`, `/tests`, `/README.md`, `/LICENSE`, `/CHANGELOG.md`, `/pyproject.toml`) as
     defense-in-depth alongside the `.gitignore` fix.
   - Fixed `Homepage` URL to the real repository.
   - Changed `license = { file = "LICENSE" }` to `license = "Apache-2.0"` (SPDX
     expression) + `license-files = ["LICENSE"]`; removed the now-redundant
     `"License :: OSI Approved :: Apache Software License"` classifier.
   - Added `"build>=1.2"` to `dev` optional-dependencies.
   - Added `addopts = "-ra -m \"not packaging\""` and a `packaging` pytest marker so the
     new slow clean-install tests are excluded from the default `pytest` run but can be
     invoked explicitly.
3. **`.github/workflows/ci.yml`**: added a new `packaging` job (matrix Python 3.10/3.11/3.12)
   that builds wheel+sdist, inspects artifact contents, installs the wheel into a fresh
   venv, imports `ragtorch` and its full documented public API from that clean install,
   runs a consumer smoke test, and runs the new `tests/packaging/` suite. The existing
   `test` job's `python -m build` step was left unchanged.
4. **`README.md`**: replaced `## Install (development)` with a `## Install` section that
   explicitly states `ragtorch` is not yet on PyPI, documents the development install
   (`pip install -e ".[dev]"`) separately from building/installing a real wheel
   (`python -m build --wheel` + `pip install dist/ragtorch-*.whl`), and notes the wheel's
   zero-runtime-dependency, provider-independent nature.
5. **`tests/packaging/test_clean_install.py`** (new): 11 tests, detailed in Phase 4.

## Phase 3 — Artifact verification (Audited, Locally verified)

- Rebuilt wheel and sdist after each fix via `python -m build`; both succeeded.
- Wheel `METADATA` re-inspected after the license fix: shows `License-Expression:
  Apache-2.0`, file shrank from full-license-embedded (~18KB) to ~5.2KB.
- Wheel content re-inspected via `zipfile`: only `ragtorch/**/*.py` plus standard wheel
  metadata (`METADATA`, `RECORD`, `WHEEL`, `licenses/LICENSE`) — no test files, no
  `__pycache__`, no `.claude`, no `.env`.
- Sdist content re-inspected via `tarfile` after the `.gitignore`/allowlist fix:
  `.claude/scheduled_tasks.lock` no longer present.
- **Experiment to isolate which fix was load-bearing**: temporarily reverted only the
  explicit `[tool.hatch.build.targets.sdist]` allowlist (keeping the `.gitignore` fix)
  and re-ran the sdist regression test — it still passed. This proves the `.gitignore`
  fix alone was sufficient for this specific defect, and the explicit allowlist is
  genuine defense-in-depth, not strictly required. Both fixes were restored and kept.
- Clean-install verification performed locally on Python 3.10 and Python 3.12 (via the
  Windows `py` launcher): built a real wheel via subprocess, created an isolated `venv`
  (no `-e`, no dev deps), installed only the wheel, and ran code with `cwd` outside the
  repository. `ragtorch.__file__` contained `site-packages` and differed from
  `src/ragtorch/__init__.py`, confirming the installed artifact — not the source
  checkout — was exercised. Python 3.11 is not available locally via the `py` launcher;
  deferred to the CI matrix, consistent with this project's established pattern (e.g.
  Step 24) of relying on the real CI matrix for full 3-version confirmation.
- Full documented public API (`ragtorch.__all__`, minus `__version__`) imported
  successfully from the clean install.
- Consumer smoke test (`Sequential(UpperCase(), Reverse())("hello") == "OLLEH"`) passed
  against the installed artifact.
- Installed version matched `pyproject.toml`'s authoritative `0.4.0`.

## Phase 4 — Testing

New file `tests/packaging/test_clean_install.py`, marked `packaging`, excluded from the
default `pytest` run (see `addopts`), run explicitly via `pytest -m packaging
tests/packaging/` or the new CI `packaging` job. 11 tests:

1. `test_wheel_builds_successfully`
2. `test_import_ragtorch_from_clean_install`
3. `test_installed_version_matches_pyproject`
4. `test_documented_public_api_imports_from_clean_install`
5. `test_full_all_export_list_imports_from_clean_install`
6. `test_installed_package_is_functional_end_to_end`
7. `test_ragtorch_file_location_is_the_installed_site_packages_not_the_checkout`
8. `test_wheel_contains_only_intended_runtime_files`
9. `test_sdist_does_not_contain_local_dev_tooling_artifacts` (regression test for the
   exact `.claude/` leak found in this step's audit)
10. `test_dev_only_dependencies_are_not_runtime_dependencies`
11. `test_build_and_install_artifacts_stay_outside_the_repository_checkout`

**Local full-suite results** (last run before commit):
- Default suite (`pytest -q`): **528 passed, 11 deselected** in 0.91s.
- Packaging suite (`pytest -q -m packaging tests/packaging/`): **11 passed** in 36.78s
  (genuinely builds artifacts, creates venvs, installs the wheel — not mocked).
- `ruff check .`: all checks passed.
- `ruff format --check .`: all files already formatted (153 files).
- `mypy`: Success, no issues found in 27 source files.

## Phase 5 — Dependency audit

- `pyproject.toml`'s `[project] dependencies = []` — confirmed zero runtime
  dependencies, unchanged by this step.
- `dev` optional-dependencies: `pytest`, `pytest-cov`, `ruff`, `mypy`, `build` — all
  dev-only, never referenced from `dependencies`. `build>=1.2` added in this step
  because the packaging tests and CI job both invoke `python -m build` and the project
  should declare that tool explicitly rather than relying on it being present by chance.
- Pinned via `test_dev_only_dependencies_are_not_runtime_dependencies`, which parses
  `pyproject.toml` directly (via `tomllib`) rather than trusting prose documentation.
- Core package remains fully offline/provider-independent — no network, LLM, embedding,
  or vector-store dependency exists anywhere in `dependencies` or the runtime import
  surface.

## Phase 6 — Security audit (package artifacts)

- Wheel: audited for `.env`, `.claude`, `__pycache__`, `.pyc`/`.pyo`, and any file
  outside `ragtorch/` — none found; pinned by
  `test_wheel_contains_only_intended_runtime_files`.
- Sdist: audited for `.claude`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.venv`,
  `.env`, `.coverage` — none found after the fix; pinned by
  `test_sdist_does_not_contain_local_dev_tooling_artifacts`.
- No secrets, credentials, or `.env`-pattern files exist anywhere in the repository
  checkout itself (not merely excluded from artifacts) — confirmed by the same scan
  finding zero matches rather than relying on exclusion alone.

## Phase 7 — Compatibility review

- No production code (`src/ragtorch/**`) was changed in this step — confirmed via
  `git diff --stat` showing changes confined to `.gitignore`, `pyproject.toml`,
  `.github/workflows/ci.yml`, `README.md`, and the new `tests/packaging/` directory.
- Public import surface (`ragtorch.__all__`) is unchanged by this step.
- The license metadata change (`license = {file=...}` → SPDX string) changes wheel
  METADATA content but not package behavior, import surface, or installed files.
- No breaking change to any existing test, API, or CI job's existing steps; the new
  `packaging` job is additive.

## Phase 8 — Exact changed files

```
 .github/workflows/ci.yml           | modified (new `packaging` job appended)
 .gitignore                         | modified (added `.claude/`)
 README.md                          | modified (`## Install` section rewritten)
 pyproject.toml                     | modified (license metadata, sdist allowlist,
                                       Homepage URL, dev deps, pytest marker/addopts)
 tests/packaging/test_clean_install.py | new (11 tests)
 evaluation/step25-evaluation.md    | new (this file)
```

No other files touched. No production source (`src/ragtorch/**`) modified.

## Phase 9 — Requirements matrix

This step resolves a concrete, previously-undocumented gap: CI never tested the actual
built package artifact outside the source checkout, and the sdist accidentally included
a local development artifact. Both are now closed with direct evidence. Appending row
**A77** to `docs/architecture/requirements-matrix-v0.1.md` (next free ID verified via
direct `grep` against the live file before use, not assumed) after GitHub-facing work
completes, per the append-only convention — historical rows A1-A76 are not rewritten.

## Phase 10 — CI / merge / post-merge (CI-proven)

- PR: [#32](https://github.com/payamfirouzfar/RAG-MODULE/pull/32)
- First PR CI run [32072204641](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32072204641)
  at commit `e3d4698` **failed**: `packaging (3.10)` job failed with
  `ModuleNotFoundError: No module named 'tomllib'` in
  `test_dev_only_dependencies_are_not_runtime_dependencies` — `tomllib` is Python
  3.11+-only stdlib, absent on 3.10. This was a real, previously-undetected defect (not
  exercised locally because the dev `.venv`'s interpreter differed); root-caused and
  fixed by falling back to the `tomli` backport (`try: import tomllib / except
  ModuleNotFoundError: import tomli as tomllib`), declared as a conditional dev
  dependency (`tomli>=2.0; python_version < '3.11'`) and installed directly in the CI
  `packaging` job's tooling step (which intentionally does not use the `dev` extras).
  Fix verified locally against a real Python 3.10.11 interpreter
  (`py -3.10 -m pytest -q -m packaging ...::test_dev_only_dependencies_are_not_runtime_dependencies`
  — 1 passed) before pushing, not merely assumed.
- Second PR CI run [32072547308](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32072547308)
  at commit `692cdef` (current PR head at merge time) — **all 6 jobs succeeded**:
  `test` × {3.10, 3.11, 3.12} and `packaging` × {3.10, 3.11, 3.12}.
- PR diff scope verified via `gh pr view --json files` immediately before merge: exactly
  the six files listed in Phase 8, no `src/ragtorch/**` changes.
- Merged via `gh pr merge 32 --merge`. Merge SHA verified directly via
  `gh pr view --json mergeCommit`: **`a7ee77195b225e27ce543ae65d1f7cd092e50a0c`**.
- Post-merge CI run [32072645810](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32072645810)
  on `main`, head SHA confirmed as the exact merge commit `a7ee771` — **all 6 jobs
  succeeded**:
  - `test (3.10)`, `test (3.11)`, `test (3.12)`: **528 passed, 11 deselected** each
    (collected 539 items / 11 deselected / 528 selected).
  - `packaging (3.10)`, `packaging (3.11)`, `packaging (3.12)`: **11 passed** each; wheel
    inspection reported **31 entries, all checks passed**; consumer smoke test passed on
    all three.
- Local branch fast-forwarded to `a7ee771` (`git checkout main && git pull`), confirmed
  via `git log --oneline -3`.

**Final closure status: Step 25 COMPLETE**, evidenced by real post-merge GitHub Actions
CI on the actual merged `main` commit — not local tests, not PR-CI alone.
