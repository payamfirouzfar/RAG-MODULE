"""The RAG pipeline, composed with ragtorch.Sequential.

DESIGN DECISION (documented per the task instruction's requirement):
Sequential.forward() is a strict `value = step(value)` chain -- verified
directly against the installed ragmodel==0.5.0 package via
inspect.getsource(Sequential.forward) before choosing this design, not
assumed. Each stage in this RAG pipeline (retrieve -> rerank ->
build_prompt -> generate) needs BOTH the original query AND the
accumulating retrieval/prompt state, which does not fit a bare
value-in/value-out chain without forcing every Module to unpack/repack
a tuple (an "unnatural architecture" per the task's own warning).

Instead, every stage's Module receives and returns a single immutable
PipelineState value object -- the RAG-equivalent of threading an
accumulator through Sequential's existing single-value contract. This
keeps Sequential itself perfectly natural to use (this is exactly what
it's for: composing single-input/single-output Modules in order) while
avoiding tuple-unpacking hacks. Block/CompositionGraph were considered
and rejected: this pipeline is a strictly linear five-stage chain with
no branching, fan-in, or fan-out, so CompositionGraph's DAG/port
machinery would add real complexity (typed ports, connection wiring)
for zero benefit over Sequential here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ragtorch import ExecutionEngine, Module, ObservabilityLevel, RunStatus, Sequential

from .prompt_builder import build_prompt
from .reranker import Reranker, maybe_rerank
from .retriever import RetrievalResult, Retriever


@dataclass(frozen=True)
class PipelineState:
    """The single value threaded through every Sequential step."""

    question: str
    results: list[RetrievalResult] = field(default_factory=list)
    prompt: str = ""
    answer: str = ""
    sources: list[dict] = field(default_factory=list)


class RetrieveStage(Module):
    def __init__(self, retriever: Retriever) -> None:
        super().__init__()
        self._retriever = retriever

    def forward(self, state: PipelineState, *, context=None) -> PipelineState:
        results = self._retriever(state.question, context=context)
        return replace(state, results=results)


class RerankStage(Module):
    def __init__(self, reranker: Reranker | None) -> None:
        super().__init__()
        self._reranker = reranker

    def forward(self, state: PipelineState, *, context=None) -> PipelineState:
        results = maybe_rerank(self._reranker, state.question, state.results)
        return replace(state, results=results)


class PromptStage(Module):
    def forward(self, state: PipelineState, *, context=None) -> PipelineState:
        prompt = build_prompt(state.question, state.results)
        return replace(state, prompt=prompt)


class GenerateStage(Module):
    def __init__(self, generator: Module, *, mode: str) -> None:
        super().__init__()
        self._generator = generator
        self._mode = mode

    def forward(self, state: PipelineState, *, context=None) -> PipelineState:
        if self._mode == "offline":
            output = self._generator((state.question, state.results), context=context)
        else:
            output = self._generator((state.question, state.results, state.prompt), context=context)
        return replace(state, answer=output["answer"], sources=output["sources"])


def build_pipeline(
    *, retriever: Retriever, reranker: Reranker | None, generator: Module, mode: str
) -> Sequential:
    return Sequential(
        RetrieveStage(retriever),
        RerankStage(reranker),
        PromptStage(),
        GenerateStage(generator, mode=mode),
    )


@dataclass(frozen=True)
class PipelineResult:
    question: str
    answer: str
    sources: list[dict]
    run_status: RunStatus
    trace_render: str


def run_pipeline(
    pipeline: Sequential, question: str, *, engine: ExecutionEngine | None = None
) -> PipelineResult:
    """Runs the pipeline through ragtorch.ExecutionEngine, capturing
    Run/Trace/status -- not just calling pipeline(question) directly."""
    engine = engine or ExecutionEngine(level=ObservabilityLevel.DEBUG)
    execution_result = engine.execute(pipeline, PipelineState(question=question))
    final_state: PipelineState = execution_result.output
    return PipelineResult(
        question=question,
        answer=final_state.answer,
        sources=final_state.sources,
        run_status=execution_result.run.status,
        trace_render=execution_result.trace.render(),
    )
