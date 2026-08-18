# Releasing ragtorch (published on PyPI as `ragmodel`)

This is the deterministic release procedure for publishing a new
`ragtorch` version to PyPI (Step 28, ADR-024). Follow every step in
order — do not skip the post-publication verification.

Note the distribution/import name split: the PyPI project name is
`ragmodel` (`pip install ragmodel`), but the Python import name remains
`ragtorch` (`import ragtorch`) — this only affects `pyproject.toml`'s
`name` field and install-command documentation; nothing else changes.

## Prerequisites (one-time setup, not part of a normal release)

1. A PyPI project named `ragmodel` must exist, with **Trusted
   Publishing** configured to trust this repository
   (`payamfirouzfar/RAG-MODULE`), the `release.yml` workflow filename,
   and the `pypi` GitHub Environment. This is configured on
   [pypi.org](https://pypi.org) by a PyPI account owner — it cannot be
   done from this repository alone. No PyPI API token is stored in
   GitHub secrets; `release.yml`'s `publish` job authenticates via
   OIDC (`permissions: id-token: write`).
2. A GitHub Environment named `pypi` must exist on this repository
   (Settings → Environments), ideally with required reviewers, so
   publication requires explicit approval even when a tag is pushed.

## Release procedure

1. **Update the version.** Bump `pyproject.toml`'s `version` field
   according to [ADR-024](architecture/decisions/ADR-024-versioning-and-release-policy.md)
   (pre-1.0: `MINOR` bump per named step/feature, `PATCH` for
   backward-compatible fixes only).
2. **Update `CHANGELOG.md`.** Add a new entry under the new version,
   following the existing "Keep a Changelog" format. Explicitly note
   any breaking change to `ragtorch.__all__`.
3. **Run complete local validation:**
   ```bash
   pytest -q
   pytest -q -m packaging tests/packaging/
   ruff check .
   ruff format --check .
   mypy
   ```
4. **Build wheel + sdist locally and inspect:**
   ```bash
   python -m build --outdir dist .
   python -m zipfile -l dist/*.whl
   ```
5. **Install the wheel into a fresh environment and run the consumer
   smoke test** (exactly what `tests/packaging/test_clean_install.py`
   already automates — run it explicitly to double-check before
   opening the PR):
   ```bash
   python -m venv /tmp/release-check
   /tmp/release-check/bin/python -m pip install dist/ragmodel-*.whl
   cd /tmp && /tmp/release-check/bin/python -c "import ragtorch; print(ragtorch.__version__)"
   ```
6. **Open a PR** with the version bump, CHANGELOG entry, and any other
   release-relevant changes.
7. **Wait for PR CI** (`ci.yml`'s `test` + `packaging` jobs, all three
   Python versions) to go green on the actual PR commit.
8. **Merge** only after CI passes. Verify the merge SHA directly
   (`gh pr view --json mergeCommit`), never trust cached metadata.
9. **Wait for post-merge CI** on the exact merged SHA on `main` to go
   green.
10. **Create and push a release tag** matching the version exactly:
    ```bash
    git tag v0.5.0
    git push origin v0.5.0
    ```
    Pushing this tag triggers `release.yml`.
11. **`release.yml`'s `build-and-validate` job** rebuilds the wheel/sdist
    from the tagged commit, verifies the tag matches
    `pyproject.toml`'s version exactly (refuses to proceed on a
    mismatch), inspects artifact contents, and runs a public-package
    smoke test against a clean install — independently of anything
    done locally in steps 4-5, since this is what actually gets
    published.
12. **The `publish` job** runs only if the `build-and-validate` job
    succeeded, and only on a tag push (or an explicit
    `workflow_dispatch` with the typed confirmation phrase) — never
    automatically from a PR or a plain push to `main`. It requires the
    `pypi` GitHub Environment's approval gate (if configured) and
    publishes via PyPI Trusted Publishing — no stored API token.
13. **The `verify-publication` job** waits briefly for PyPI's index to
    reflect the new release, then installs the just-published version
    from PyPI itself (`pip install ragmodel`, not the local wheel) into
    a fresh environment and runs a smoke test — the only step that
    actually proves the public release works, as opposed to proving the
    pre-publication artifact worked.
14. **A GitHub release is created automatically** (tag-triggered runs
    only) with auto-generated release notes from the tag.
15. **Record evidence** in `evaluation/step<N>-evaluation.md` or the
    relevant step's ledger: the PyPI version now live, the exact
    `pip install ragmodel` clean-install verification output, the
    `release.yml` run ID, and the GitHub release URL.

## What must NEVER happen

- A pull request must never trigger `publish` — `release.yml`'s
  `on:` block only listens for `push: tags: v*` and
  `workflow_dispatch`, neither of which fires from a PR.
- `ci.yml` (the normal branch/PR validation workflow) must never gain a
  publish step — publication lives exclusively in `release.yml`.
- No PyPI API token should ever be added to this repository's secrets.
  Trusted Publishing (OIDC) is the only supported authentication path;
  if it cannot be configured, publication is blocked, not
  worked around with a stored token.
- Publication must never be claimed as complete without the
  `verify-publication` job's actual `pip install ragmodel` evidence —
  a successful `publish` job alone (PyPI accepted the upload) is not
  the same claim as "a real user can now install this," even though in
  practice they usually coincide.
