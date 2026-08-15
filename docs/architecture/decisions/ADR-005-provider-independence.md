# ADR-005: Provider Independence

## Context

Step 2 adds execution, observability, and evaluation infrastructure —
no LLM, embedding, or vector-store integration exists yet, and later steps
will add them. Before any of that lands, we need to commit to how those
integrations will relate to the core, because the answer shapes their
design from their first line of code. Get this wrong and `ragtorch` becomes
"a framework that happens to require OpenAI" or "a framework that happens
to require a specific vector database" — which defeats the stated goal of
letting a developer run a fully local, zero-API-cost RAG system on their
own machine.

## Decision

`ragtorch` core (and, by extension, `ragtorch.evaluation`) must never
import or require a specific model provider, embedding service, vector
database, or orchestration framework (OpenAI, Anthropic, Qdrant, Milvus,
LangChain, LangGraph, etc.). Provider-specific code is an adapter that
implements a stable interface defined in core (e.g. a future `Generator`,
`Embedder`, `Retriever` protocol) and ships as an **optional dependency
group**, per the `pyproject.toml` optional-dependencies mechanism already
used for `ragtorch[dev]`:

```text
pip install ragtorch            # tiny core, no vendor deps
pip install "ragtorch[ollama]"   # + Ollama adapter
pip install "ragtorch[huggingface]"
pip install "ragtorch[qdrant]"
pip install "ragtorch[all]"
```

This applies retroactively to everything built in Step 2: `Evaluator`
accepts any callable system, not specifically a `ragtorch.core.Module`, so
evaluation works identically whether the thing being evaluated calls a
local model or a paid API — the framework cannot tell the difference and
must not need to.

## Alternatives considered

- **Ship a default LLM integration "for convenience."** Rejected: any
  default (even an ostensibly neutral one) becomes a de facto dependency
  that every installation pays for, and privileges one vendor's cost model
  and availability over local/free alternatives — directly against the
  "vendor independence" and "local-first" requirements.
- **Integrate LangChain/LangGraph as the orchestration layer under the
  hood.** Rejected for core: it would make `ragtorch`'s own `Module`/
  `Sequential` abstractions redundant or, worse, thin wrappers around
  someone else's object model, undermining the "stable interfaces,
  replaceable implementations" principle from Step 1. A LangChain/
  LangGraph *adapter* — code that lets ragtorch components be used inside
  a LangGraph graph, or vice versa — is a legitimate optional integration,
  built alongside other adapters, not a foundation dependency.

## Consequences

- A user can build and evaluate a complete pipeline using only free, local
  models and never install a vendor SDK.
- Every future "Step N: add X provider" (Ollama, Hugging Face, OpenAI,
  Qdrant, ...) is additive: it introduces a new optional dependency group
  and an adapter module, never a change to what `pip install ragtorch`
  pulls in by default.
- `ragtorch.evaluation.Evaluator` (built in this step) already satisfies
  this ADR by construction — it evaluates an arbitrary callable, so no
  future retrofit is needed when provider adapters exist.
