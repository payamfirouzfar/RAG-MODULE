# ADR-004: Evaluation Architecture

## Context

RAG systems fail in ways unit tests don't catch: a retriever can still
return *something* for every query while its recall silently degrades, a
prompt change can make answers subtly less faithful without throwing any
exception. Waiting until chunking/retrieval/generation exist before
building evaluation would mean bolting quality measurement onto a system
already built without it in mind — and would tempt every future evaluation
need toward "hard-code an LLM judge," which conflates evaluation with one
model-dependent technique for it.

## Decision

Build evaluation now, in `ragtorch.evaluation`, as a small set of composable
abstractions:

- **`EvaluationCase`**: one input (+ optional expected output, name,
  metadata). `expected` is optional because not every metric needs ground
  truth — latency and cost metrics just observe behavior.
- **`Metric`**: a `Protocol` with a `name` and a `score(case, actual)`
  method returning a float. Nothing about this interface is LLM-shaped.
  `ExactMatch` and `Latency` need no model at all; a future
  `LLMJudgeMetric` or `FaithfulnessMetric` is just another implementation
  of the same interface, not a case the `Evaluator` needs special-cased
  branches for.
- **`Evaluator`**: runs any callable system (a `Module`, a `Sequential`, or
  a plain function — evaluation does not require `ragtorch.core`) over a
  sequence of cases and a sequence of metrics, isolating failures per-case
  and per-metric so one broken case doesn't abort the whole run.
- **`EvaluationResult`**: the machine-readable outcome — per-case scores,
  error count, duration, and (when available) `git_commit` and
  `configuration_hash`, plus `to_dict()` for serialization. Capturing the
  git commit answers "which code produced this number?" so two evaluation
  runs can be meaningfully compared across a code change; capturing a
  configuration hash acknowledges that *same code + different config* is
  a different experiment.

## Alternatives considered

- **`LLMEvaluator` as the fundamental abstraction.** Rejected: it would
  make every non-LLM metric (latency, cost, exact match, recall@k) feel
  like a workaround instead of the normal case, and would force a model
  dependency into evaluation from day one.
- **Wait until Step 8 (RAG pipeline) to add evaluation.** Rejected per the
  project's own rule ("evaluation at every step") — retrofitting evaluation
  after chunking/retrieval/generation exist means those components get
  built without a quality feedback loop, which is precisely the outcome
  we're trying to avoid.
- **Bury evaluation results only as printed output.** Rejected:
  `EvaluationResult.to_dict()` produces a JSON-shaped artifact specifically
  so future CI can diff two evaluation runs and fail on regression (a later
  step), not just so a human can read a printout once.

## Consequences

- Every future component (chunker, retriever, router, generator) can be
  evaluated through the same three-line pattern: cases, metrics, evaluate.
- Evaluation has zero dependency on `ragtorch.core` — a user can evaluate
  an arbitrary Python callable, not only a `Module`.
- CI-based evaluation regression detection (a later step) has a stable
  artifact shape to compare against, because `EvaluationResult` already
  captures the identity fields (commit, config hash) needed to make
  "compare evaluation A vs. evaluation B" meaningful.
