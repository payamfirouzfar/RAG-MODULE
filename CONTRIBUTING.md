# Contributing

Thanks for your interest in `ragtorch`.

## Development setup

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
```

## Before opening a pull request

```bash
ruff format .
ruff check .
mypy
pytest
```

All of the above must pass. CI enforces the same checks.

## Commit style

Each commit should be one coherent change explainable in one sentence, e.g.:

```text
feat(core): add Sequential composition
test(core): add module registration contract tests
fix(core): wrap forward() exceptions in ExecutionError
```

## API stability

Public API lives in `ragtorch.__init__` and `ragtorch.core.__init__`.
Anything under a leading underscore, or not re-exported there, is internal
and may change without notice.

## Scope of this project

Step 1 is a dependency-free core kernel. Do not add LLM, embedding, vector
database, or orchestration-framework dependencies to `src/ragtorch/core`.
Those integrations belong in later, separately-scoped modules.
