# ragtorch

A modular framework kernel for building RAG (retrieval-augmented generation)
systems. `ragtorch` is the package name for now — it can be renamed before
public release without changing the underlying design.

## Status

**Step 2 — Execution, Observability & Evaluation Kernel.** This repository
contains the core kernel (`Module`, `RAGModule`, `Sequential`,
configuration, errors, events) plus execution identity (`ExecutionContext`,
`Run`), observability (`Trace`/`Span`, `MetricsCollector`, structured
logging), and a model-agnostic evaluation framework (`ragtorch.evaluation`).
There is intentionally **no LLM, embedding, vector store, or orchestration
integration yet**. Those are built on top of this foundation in later
steps — see `docs/architecture/requirements.md` for the vendor/model/
storage-independence rules that will govern them.

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

Evaluating any callable system (no LLM required):

```python
from ragtorch.evaluation import EvaluationCase, Evaluator, ExactMatch

cases = [
    EvaluationCase(input="ab", expected="BA", name="case-1"),
    EvaluationCase(input="hi", expected="IH", name="case-2"),
]
result = Evaluator([ExactMatch()]).evaluate(pipeline, cases)
print(result.mean("exact_match"))  # 1.0
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
src/ragtorch/core/         core kernel + execution/observability primitives
src/ragtorch/evaluation/    model-agnostic evaluation framework
tests/unit/                  unit tests
tests/integration/            integration tests
docs/architecture/decisions/    ADRs
docs/architecture/requirements.md   frozen project-wide requirements
evaluation/                       milestone evaluation reports and benchmarks
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
