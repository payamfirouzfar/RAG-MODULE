"""Evaluation module tests: hit@1, hit@k, MRR, citation presence,
negative-question detection."""

from __future__ import annotations

from src.evaluation import EvalCase, evaluate_case, summarize
from src.generator import INSUFFICIENT_EVIDENCE_MESSAGE
from src.pipeline import PipelineResult
from src.retriever import RetrievalResult

from ragtorch import RunStatus


def _result(doc_id: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=f"{doc_id}::0",
        document_id=doc_id,
        text="text",
        url="http://x",
        title="T",
        score=0.9,
    )


def _pipeline_result(answer: str, sources: list) -> PipelineResult:
    return PipelineResult(
        question="q",
        answer=answer,
        sources=sources,
        run_status=RunStatus.SUCCEEDED,
        trace_render="",
    )


def test_hit_at_1_true_when_expected_doc_is_first():
    case = EvalCase(question="q", expected_document_id="d1")
    results = [_result("d1"), _result("d2")]
    eval_result = evaluate_case(
        case,
        results,
        _pipeline_result("answer", [{"chunk_id": "d1::0"}]),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    assert eval_result.hit_at_1 is True
    assert eval_result.hit_at_k is True
    assert eval_result.reciprocal_rank == 1.0


def test_hit_at_1_false_but_hit_at_k_true_when_expected_doc_is_second():
    case = EvalCase(question="q", expected_document_id="d2")
    results = [_result("d1"), _result("d2")]
    eval_result = evaluate_case(
        case,
        results,
        _pipeline_result("answer", []),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    assert eval_result.hit_at_1 is False
    assert eval_result.hit_at_k is True
    assert eval_result.reciprocal_rank == 0.5


def test_hit_at_k_false_when_expected_doc_not_retrieved():
    case = EvalCase(question="q", expected_document_id="d99")
    results = [_result("d1"), _result("d2")]
    eval_result = evaluate_case(
        case,
        results,
        _pipeline_result("answer", []),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    assert eval_result.hit_at_1 is False
    assert eval_result.hit_at_k is False
    assert eval_result.reciprocal_rank == 0.0


def test_negative_case_correctly_flagged():
    case = EvalCase(question="q", expected_document_id=None, is_negative=True)
    eval_result = evaluate_case(
        case,
        [],
        _pipeline_result(INSUFFICIENT_EVIDENCE_MESSAGE, []),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    assert eval_result.correctly_flagged_insufficient is True


def test_negative_case_incorrectly_answered():
    case = EvalCase(question="q", expected_document_id=None, is_negative=True)
    eval_result = evaluate_case(
        case,
        [_result("d1")],
        _pipeline_result("Paris is the capital.", [{"chunk_id": "d1::0"}]),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    assert eval_result.correctly_flagged_insufficient is False


def test_citation_presence_detected():
    case = EvalCase(question="q", expected_document_id="d1")
    eval_result = evaluate_case(
        case,
        [_result("d1")],
        _pipeline_result("answer", [{"chunk_id": "d1::0"}]),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    assert eval_result.has_citation is True


def test_summarize_computes_correct_rates():
    case1 = EvalCase(question="q1", expected_document_id="d1")
    case2 = EvalCase(question="q2", expected_document_id="d2")
    r1 = evaluate_case(
        case1,
        [_result("d1")],
        _pipeline_result("a", [{"chunk_id": "d1::0"}]),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    r2 = evaluate_case(
        case2,
        [_result("d99")],
        _pipeline_result("a", []),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    summary = summarize([r1, r2])
    assert summary.case_count == 2
    assert summary.hit_at_1_rate == 0.5
    assert summary.citation_presence_rate == 0.5


def test_summarize_handles_empty_list():
    summary = summarize([])
    assert summary.case_count == 0
    assert summary.hit_at_1_rate == 0.0


def test_summary_render_includes_negative_case_stats():
    case = EvalCase(question="q", expected_document_id=None, is_negative=True)
    r = evaluate_case(
        case,
        [],
        _pipeline_result(INSUFFICIENT_EVIDENCE_MESSAGE, []),
        insufficient_evidence_marker=INSUFFICIENT_EVIDENCE_MESSAGE,
    )
    summary = summarize([r])
    rendered = summary.render()
    assert "negative-question correctness" in rendered
