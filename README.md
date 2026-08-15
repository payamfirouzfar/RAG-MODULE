# ragtorch

A modular framework kernel for building RAG (retrieval-augmented generation)
systems. `ragtorch` is the package name for now — it can be renamed before
public release without changing the underlying design.

## Status

**Step 1 — Framework Kernel.** This repository currently contains only the
core kernel: `Module`, `RAGModule`, `Sequential`, configuration, errors, and
events. There is intentionally **no LLM, embedding, vector store, or
orchestration integration yet**. Those are built on top of this foundation
in later steps.

## Design principle

> Stable interfaces + replaceable implementations + observable execution +
> measurable behavior.

See [docs/architecture/decisions/ADR-001-core-module-abstraction.md](docs/architecture/decisions/ADR-001-core-module-abstraction.md)
for the reasoning behind the core `Module` contract.

## Install (development)

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -e ".[dev]"
```

## Quick example

```python
from ragtorch import Module, Sequential


class UpperCase(Module):
    def forward(self, input):
        return input.upper()


class Reverse(Module):
    def forward(self, input):
        return input[::-1]


pipeline = Sequential(UpperCase(), Reverse())
print(pipeline("hello"))  # "OLLEH"
print(pipeline.inspect())
```

## Development

```bash
pytest                      # run tests
ruff check .                # lint
ruff format .                # format
mypy                         # type check
```

## Repository layout

```text
src/ragtorch/core/    core kernel (Module, Sequential, config, errors, events)
tests/unit/            unit tests
tests/integration/      integration tests
docs/architecture/decisions/   ADRs
evaluation/            milestone evaluation reports
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
