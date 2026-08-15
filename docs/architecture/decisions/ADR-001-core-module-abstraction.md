# ADR-001: Core Module Abstraction

## Context

`ragtorch` needs one abstraction that every future component (chunkers,
retrievers, routers, generators, and eventually full RAG systems) can build
on. Without it, every subsystem would invent its own composition, error
handling, and observability conventions, and nothing would compose.

We considered modeling this on PyTorch's `nn.Module`, since it's a proven
pattern for composable, inspectable components. But RAG systems are not
neural networks: they involve documents, external services, network calls,
and non-differentiable operations. Copying `nn.Module`'s implementation
details (parameters, gradients, device placement) would be wrong.

## Decision

Adopt a minimal `Module` contract:

- `forward(input)` holds a component's actual logic; subclasses implement it.
- `__call__(input)` is the framework-level entry point (currently: emits
  `MODULE_STARTED`/`MODULE_FINISHED`/`MODULE_FAILED` events and wraps
  unexpected exceptions in `ExecutionError`). Callers always use `__call__`.
- Child modules assigned as attributes (`self.retriever = Retriever()`) are
  automatically registered, mirroring `nn.Module` ergonomics, giving us
  `named_modules()`/`modules()`/`inspect()` for free.
- `RAGModule` is a marker subclass with no added behavior, used to identify
  top-level RAG systems via `isinstance`.

We take the *abstraction* from PyTorch (composable, inspectable, callable
components with a clean forward/call split) but not the *implementation*
(no parameters, tensors, autograd, or device management).

## Alternatives considered

- **Plain functions + a pipeline runner.** Simpler, but loses discoverability
  (`named_modules`), a natural registration mechanism, and a place to hang
  cross-cutting concerns (events, config) without threading them through
  every function signature.
- **Directly subclass `torch.nn.Module`.** Rejected: it would force a hard
  PyTorch dependency into the core, violating the "core has zero vendor
  dependencies" rule, and would carry irrelevant tensor/autograd machinery.

## Consequences

- Every future component (`Chunker`, `Retriever`, `Router`, ...) is a
  `Module` subclass with a small, consistent interface.
- Composition (`Sequential`, and later graph-based execution) works uniformly
  over any `Module`.
- Adding cross-cutting behavior (tracing, profiling, validation) later means
  extending `__call__`, not touching every subclass's `forward`.
- The core has zero runtime dependencies, satisfying the "small, stable,
  easy to install" goal for the framework kernel.
