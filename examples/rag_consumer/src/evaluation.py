"""RAG evaluation: retrieval hit@1/hit@k, MRR, answer/citation presence.

This is explicitly a small application-level smoke/evaluation dataset,
not a scientifically rigorous RAG benchmark -- labeled as such
everywhere it is reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .pipeline import PipelineResult
from .retriever import RetrievalResult


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_document_id: str | None  # None for negative (unanswerable) questions
    expected_keyword: str | None = None  # a keyword the answer should contain if answerable
    is_negative: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCaseResult:
    case: EvalCase
    retrieval_results: list[RetrievalResult]
    pipeline_result: PipelineResult
    hit_at_1: bool
    hit_at_k: bool
    reciprocal_rank: float  # 0.0 if not found in results
    has_citation: bool
    correctly_flagged_insufficient: bool | None  # None if not a negative case


def _rank_of_expected(results: list[RetrievalResult], expected_document_id: str) -> int | None:
    for i, r in enumerate(results):
        if r.document_id == expected_document_id:
            return i + 1  # 1-indexed rank
    return None


def evaluate_case(
    case: EvalCase,
    retrieval_results: list[RetrievalResult],
    pipeline_result: PipelineResult,
    *,
    insufficient_evidence_marker: str,
) -> EvalCaseResult:
    if case.is_negative:
        correctly_flagged = insufficient_evidence_marker.lower() in pipeline_result.answer.lower()
        return EvalCaseResult(
            case=case,
            retrieval_results=retrieval_results,
            pipeline_result=pipeline_result,
            hit_at_1=False,
            hit_at_k=False,
            reciprocal_rank=0.0,
            has_citation=len(pipeline_result.sources) > 0,
            correctly_flagged_insufficient=correctly_flagged,
        )

    assert case.expected_document_id is not None
    rank = _rank_of_expected(retrieval_results, case.expected_document_id)
    return EvalCaseResult(
        case=case,
        retrieval_results=retrieval_results,
        pipeline_result=pipeline_result,
        hit_at_1=(rank == 1),
        hit_at_k=(rank is not None),
        reciprocal_rank=(1.0 / rank) if rank is not None else 0.0,
        has_citation=len(pipeline_result.sources) > 0,
        correctly_flagged_insufficient=None,
    )


@dataclass(frozen=True)
class EvaluationSummary:
    case_count: int
    hit_at_1_rate: float
    hit_at_k_rate: float
    mean_reciprocal_rank: float
    citation_presence_rate: float
    negative_case_count: int
    negative_case_correct_rate: float | None

    def render(self) -> str:
        lines = [
            "RAG evaluation summary (small application-level smoke dataset, NOT a "
            "scientific benchmark):",
            f"  cases: {self.case_count}",
            f"  hit@1: {self.hit_at_1_rate:.2%}",
            f"  hit@k: {self.hit_at_k_rate:.2%}",
            f"  MRR:   {self.mean_reciprocal_rank:.3f}",
            f"  citation presence: {self.citation_presence_rate:.2%}",
        ]
        if self.negative_case_correct_rate is not None:
            lines.append(
                f"  negative-question correctness: {self.negative_case_correct_rate:.2%} "
                f"({self.negative_case_count} negative cases)"
            )
        return "\n".join(lines)


def summarize(results: list[EvalCaseResult]) -> EvaluationSummary:
    positive = [r for r in results if not r.case.is_negative]
    negative = [r for r in results if r.case.is_negative]

    def rate(items: list, predicate) -> float:
        return sum(1 for i in items if predicate(i)) / len(items) if items else 0.0

    return EvaluationSummary(
        case_count=len(results),
        hit_at_1_rate=rate(positive, lambda r: r.hit_at_1),
        hit_at_k_rate=rate(positive, lambda r: r.hit_at_k),
        mean_reciprocal_rank=(
            sum(r.reciprocal_rank for r in positive) / len(positive) if positive else 0.0
        ),
        citation_presence_rate=rate(results, lambda r: r.has_citation),
        negative_case_count=len(negative),
        negative_case_correct_rate=(
            rate(negative, lambda r: r.correctly_flagged_insufficient) if negative else None
        ),
    )
