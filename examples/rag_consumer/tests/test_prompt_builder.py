"""PromptBuilder tests: context included, question included,
anti-hallucination instruction included."""

from __future__ import annotations

from src.prompt_builder import build_prompt
from src.retriever import RetrievalResult


def _result(text: str, title: str = "Title", url: str = "http://x") -> RetrievalResult:
    return RetrievalResult(
        chunk_id="c1", document_id="d1", text=text, url=url, title=title, score=0.9
    )


def test_prompt_includes_question():
    prompt = build_prompt("What is the capital of France?", [])
    assert "What is the capital of France?" in prompt


def test_prompt_includes_retrieved_context():
    results = [_result("Paris is the capital of France.")]
    prompt = build_prompt("What is the capital?", results)
    assert "Paris is the capital of France." in prompt


def test_prompt_includes_anti_hallucination_instruction():
    prompt = build_prompt("question", [])
    assert "do not invent" in prompt.lower()
    assert "insufficient" in prompt.lower()


def test_prompt_includes_citation_instruction():
    prompt = build_prompt("question", [_result("evidence")])
    assert "cite" in prompt.lower()


def test_prompt_with_no_results_states_no_evidence():
    prompt = build_prompt("question", [])
    assert "no evidence" in prompt.lower()


def test_prompt_numbers_multiple_sources():
    results = [_result("first evidence"), _result("second evidence")]
    prompt = build_prompt("question", results)
    assert "[1]" in prompt
    assert "[2]" in prompt
