# ragtorch

A provider-independent Python framework for building RAG systems as composable, inspectable, and testable pieces.

**Actively developed · pre-1.0**

ragtorch is inspired by PyTorch's `Module` pattern, but it focuses on the execution, composition, observability, retrieval primitives, and evaluation layers rather than forcing a specific AI provider stack.

## Why ragtorch?

RAG applications can quickly turn into tightly connected pieces of retrieval, ranking, generation, tracing, evaluation, and application logic.

ragtorch takes a simpler approach: provide a stable execution layer and let you bring the components you actually need.

> **Stable interfaces + replaceable implementations + observable execution + measurable behavior.**

The goal is to make RAG architectures easier to compose, inspect, test, evaluate, and benchmark without tying the core to a particular LLM, vector database, or cloud provider.

## What is available today?

The current framework includes:

- **`Module`** — the main implementation base for composable components.
- **`Component`** — a minimal structural protocol that third-party classes can satisfy without inheriting from ragtorch.
- **`Sequential`** — ordered module composition.
- **`CompositionGraph`** — immutable graph-based composition.
- **`Block`** — a reusable graph-backed module that can itself be composed inside another pipeline.
- **`ExecutionPlan` + `Executor`** — deterministic planning and execution of composition graphs.
- **`ExecutionEngine`** — a common `Run` / `Trace` / `MetricsCollector` lifecycle with `OFF`, `BASIC`, and `DEBUG` observability levels.
- **`ragtorch.evaluation`** — model-agnostic evaluation for any callable system.
- **Execution context propagation** — nested execution keeps the correct parent/child relationship without global state.
- **Architecture metadata** — ports and immutable snapshots for describing component boundaries without executing them.
- **`ragtorch.retrieval`** — dependency-free retrieval primitives including `BM25Index` and Reciprocal Rank Fusion (`rrf`).

## What is intentionally not included?

ragtorch is not an all-in-one RAG application framework.

The core does not currently ship built-in:

- embedding models
- vector databases
- LLM providers
- document loaders
- chunking systems
- rerankers
- multimodal or vision providers
- Graph RAG implementations

You bring these pieces yourself and connect them through the framework's component contracts. This keeps the core small and provider-independent.

The provider-adapter question is intentionally evidence-driven rather than added just for the sake of integrations. See [ADR-005](docs/architecture/decisions/ADR-005-provider-independence.md) and the [requirements matrix](docs/architecture/requirements-matrix-v0.1.md) for the project's reasoning.

## A simple example

```python
from ragtorch import Module, Sequential


class UpperCase(Module):
    def forward(self, input):
        return input.upper()


class Reverse(Module):
    def forward(self, input):
        return input[::-1]


pipeline = Sequential(UpperCase(), Reverse())

print(pipeline("hello"))  # OLLEH
print(pipeline.inspect())
```

The same pattern can be used for a RAG-shaped application while keeping the retriever and generator under your control:

```python
from ragtorch import Module, Sequential


class Retriever(Module):
    def forward(self, query, *, context=None):
        # Replace with your own embedding model + vector store.
        return {"query": query, "docs": ["doc about " + query]}


class Generator(Module):
    def forward(self, payload, *, context=None):
        # Replace with your own LLM call.
        return f"Answer for '{payload['query']}': {payload['docs']}"


rag = Sequential(Retriever(), Generator())
print(rag("refund policy"))
```

## Retrieval primitives

`BM25Index` provides dependency-free lexical retrieval, while `rrf()` combines rankings deterministically:

```python
from ragtorch.retrieval import BM25Index, rrf

lexical = BM25Index({
    "doc-1": "Python is a programming language",
    "doc-2": "Python is also a snake",
})

lexical_ids = [item.item for item in lexical.search("Python programming")]
dense_ids = ["doc-2", "doc-1"]  # from your own dense retriever

print(rrf([dense_ids, lexical_ids]))
```

These are intentionally plain algorithms rather than `Module` objects. They do not need execution identity or lifecycle management.

## Evaluation

The evaluation layer is model-agnostic, so it can score a callable system even when that system was not built with ragtorch:

```python
from ragtorch.evaluation import EvaluationCase, Evaluator, ExactMatch

cases = [
    EvaluationCase(input="ab", expected="BA", name="case-1"),
    EvaluationCase(input="hi", expected="IH", name="case-2"),
]

result = Evaluator([ExactMatch()]).evaluate(pipeline, cases)
print(result.mean("exact_match"))  # 1.0
```

## Observable execution

```python
from ragtorch import ExecutionEngine, ObservabilityLevel

engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
result = engine.execute(pipeline, "hello")

print(result.output)            # OLLEH
print(result.run.status)        # RunStatus.SUCCEEDED
print(result.trace.render())    # indented span tree
print(result.metrics.summarize_all())
```

When modules are nested, execution context can be passed to child components so the runtime keeps the parent/child relationship without relying on global state.

## Installation

The Python import name is `ragtorch`. The published PyPI distribution is currently named `ragmodel`.

```bash
pip install ragmodel
```

```python
import ragtorch
```

The project is pre-1.0 (`0.x`), so minor releases may contain public API changes. Pin an exact version when you need a stable dependency. See [ADR-024](docs/architecture/decisions/ADR-024-versioning-and-release-policy.md) and [CHANGELOG.md](CHANGELOG.md).

### Development install

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -e ".[dev]"
```

### Build a wheel locally

```bash
python -m build --wheel
pip install dist/ragtorch-*.whl
```

The core package has zero mandatory runtime dependencies. It does not pull in an LLM, embedding provider, vector store, or network client.

## Project structure

```text
src/ragtorch/core/                  core execution + observability
src/ragtorch/evaluation/            model-agnostic evaluation
src/ragtorch/retrieval/             provider-independent retrieval
tests/unit/                          unit tests
tests/integration/                  integration tests
tests/packaging/                    packaging and clean-install tests
tests/discovery/                    architecture/consumer experiments
benchmarks/                          performance measurements
evaluation/                          per-step evaluation reports
docs/architecture/decisions/        architecture decision records
docs/architecture/requirements.md   frozen project requirements
docs/architecture/requirements-matrix-v0.1.md
                                    requirements/evidence ledger
examples/                            consumer examples
```

## Engineering approach

ragtorch is being developed step by step rather than as a large framework built all at once.

Each architectural step is treated as an engineering contract: define the behavior, implement it, test it, measure it when performance matters, document the decision, and verify it in CI.

For example, Step 16 introduced `Block` without creating a second execution system or changing the existing execution layers. The implementation was backed by unit tests, integration tests, a benchmark, evaluation evidence, and post-merge CI. The merged Step 16 work reached **406/406 tests across Python 3.10, 3.11, and 3.12**.

The repository also keeps architectural decisions and rejected alternatives visible. That is intentional: the reasoning behind a framework is part of the project, not just the final code.

## Current direction

The project is still under active development. The broader roadmap is focused on building a clean foundation for RAG and agentic systems without turning the core into a collection of unrelated integrations.

Areas being explored include:

- richer RAG primitives and composition
- evaluation and benchmarking
- process and workflow abstractions
- agents and tools
- memory
- observability
- security and human-in-the-loop capabilities
- process mining and optimization

Not every idea will become core functionality. Benchmarks, real consumer examples, and architectural evidence are used to decide what belongs in the framework.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
