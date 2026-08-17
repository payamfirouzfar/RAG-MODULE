# ragtorch

A modular, provider-independent execution kernel for building composable
RAG (retrieval-augmented generation) systems.

## What ragtorch is today

A framework kernel you compose your own RAG systems on top of:

- **`Module`/`Sequential`/`Block`/`CompositionGraph`** — the core
  composable execution primitives. `Module` is the concrete
  implementation base; `Component` is a minimal structural protocol
  (`name`, `component_type`, `__call__`) that anything can satisfy
  without inheriting from `Module` at all.
- **`ExecutionEngine`** — coordinates `Run`/`Trace`/`MetricsCollector`
  around a `Module` call as a guaranteed contract, at three
  observability levels (`OFF`/`BASIC`/`DEBUG`).
- **`ragtorch.evaluation`** — a model-agnostic evaluation framework
  (`Evaluator`, `Metric`, `EvaluationCase`) that scores any callable
  system, not only `ragtorch` components.
- **Nested execution context propagation** — composite `Module`
  execution (e.g. `Sequential`'s children) gets correctly-parented
  execution identity for each child, with zero global state.
- **Structural, immutable architecture metadata** — `InputPort`/
  `OutputPort`/`is_compatible()`/`ArchitectureSnapshot` let you describe
  and validate a component's boundary and a whole architecture's shape
  without executing anything.

## What ragtorch is not yet

ragtorch does not currently ship any built-in:

- embedding models
- vector databases
- LLM providers
- document loaders
- chunking framework
- rerankers
- multimodal or vision providers
- Graph RAG implementation

These are explicitly out of scope for the framework kernel itself (see
[docs/architecture/decisions/ADR-005-provider-independence.md](docs/architecture/decisions/ADR-005-provider-independence.md)).
You compose your own retrieval/generation components — plain classes
satisfying `Component`, or `Module` subclasses — and wire them together
with `Sequential`/`Block`/`CompositionGraph`. See the Quick example
below for a working (if deliberately simple) end-to-end pipeline built
entirely this way.

Whether and how a provider-adapter layer gets added to ragtorch itself
is an open, evidence-gated question — see
[docs/architecture/requirements-matrix-v0.1.md](docs/architecture/requirements-matrix-v0.1.md)
rows A76/A78/A79 for the audit trail. Nothing here should be read as
implying that layer is coming in any particular form or timeframe.

## Design principle

> Stable interfaces + replaceable implementations + observable execution +
> measurable behavior.

See [docs/architecture/decisions/ADR-001-core-module-abstraction.md](docs/architecture/decisions/ADR-001-core-module-abstraction.md)
for the reasoning behind the core `Module` contract.

## Install

`ragtorch` is pre-1.0 (`0.x`) — the public API may change between minor
versions; see
[ADR-024](docs/architecture/decisions/ADR-024-versioning-and-release-policy.md)
for the exact versioning policy. Pin an exact version, not a range, if
you need stability across upgrades.

### From PyPI

```bash
pip install ragtorch
```

Only use this once `ragtorch` has actually been published — check
[CHANGELOG.md](CHANGELOG.md) or the PyPI project page for the current
released version before relying on this command.

### Development install

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -e ".[dev]"
```

This installs `ragtorch` in editable mode plus development tooling
(`pytest`, `ruff`, `mypy`, `build`).

### Building and installing a real wheel locally

To build and install the actual distributable artifact (e.g. to test
it the way a real consumer would, outside the source checkout):

```bash
python -m build --wheel
pip install dist/ragtorch-*.whl
```

The wheel has zero runtime dependencies and is provider-independent --
no LLM, embedding, vector-store, or network dependency is pulled in,
and installation performs no network access or provider authentication.

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

A minimal retrieval + generation pipeline, composed entirely from your
own components (no built-in retriever/generator exists -- see "What
ragtorch is not yet" above):

```python
from ragtorch import Module, Sequential


class Retriever(Module):
    def forward(self, query, *, context=None):
        # Replace with a real embedding model + vector store/index.
        return {"query": query, "docs": ["doc about " + query]}


class Generator(Module):
    def forward(self, payload, *, context=None):
        # Replace with a real LLM call.
        return f"Answer for '{payload['query']}': {payload['docs']}"


rag = Sequential(Retriever(), Generator())
print(rag("refund policy"))
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

Executing with a guaranteed observability contract:

```python
from ragtorch import ExecutionEngine, ObservabilityLevel

engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
result = engine.execute(pipeline, "hello")
print(result.output)  # "OLLEH"
print(result.run.status)  # RunStatus.SUCCEEDED
print(result.trace.render())  # indented span tree
print(result.metrics.summarize_all())
```

A composite module's children can opt in to receiving execution context —
`Sequential` gives each step a distinct, correctly-parented child context:

```python
class Retriever(Module):
    def forward(self, query, *, context=None):
        print(f"retriever run: {context.run_id if context else None}")
        return {"query": query, "docs": ["a", "b"]}


class Generator(Module):
    def forward(self, payload, *, context=None):
        print(f"generator run: {context.run_id if context else None}")
        return f"answer for {payload['query']}"


rag = Sequential(Retriever(), Generator())
engine.execute(rag, "What is our refund policy?")
# retriever run: run_...   (distinct child of the root run)
# generator run: run_...   (a different distinct child of the root run)
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
tests/packaging/               clean-install / distribution artifact tests
tests/discovery/                 RAG-consumer discovery experiments (not public API)
docs/architecture/decisions/    ADRs
docs/architecture/requirements.md   frozen project-wide requirements
docs/architecture/requirements-matrix-v0.1.md   append-only requirements/evidence ledger
evaluation/                       per-step evaluation reports and benchmarks
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
