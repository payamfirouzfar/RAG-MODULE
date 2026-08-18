"""Generator tests: offline mode, provider mode mocked, provider
failure. No real network / API key used."""

from __future__ import annotations

import importlib.util
from unittest.mock import MagicMock, patch

import pytest
from src.generator import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    GeneratorError,
    LLMGenerator,
    OfflineGenerator,
    build_generator,
)
from src.retriever import RetrievalResult

from ragtorch import ExecutionError

_openai_installed = importlib.util.find_spec("openai") is not None
requires_openai = pytest.mark.skipif(
    not _openai_installed, reason="openai is an optional dependency, not required for core tests"
)

# NOTE on exception types below: verified directly against the installed
# ragmodel==0.5.0 package (inspect.getsource(Module.__call__)) that
# EVERY Module.__call__ -- not only calls routed through
# ExecutionEngine -- catches any non-RegistryError exception raised
# inside forward() and re-raises it wrapped as ragtorch.ExecutionError
# (with the original exception attached via __cause__). Tests that
# invoke a Module via generator(...) (i.e. __call__) must therefore
# expect ExecutionError, not the raw GeneratorError -- only a direct
# .forward(...) call bypasses that wrapping. Both call styles are
# tested below deliberately, so this distinction is exercised rather
# than assumed.


def _result(text: str = "evidence text") -> RetrievalResult:
    return RetrievalResult(
        chunk_id="c1", document_id="d1", text=text, url="http://x", title="T", score=0.9
    )


def test_offline_generator_returns_insufficient_evidence_when_empty():
    generator = OfflineGenerator()
    output = generator(("question", []))
    assert output["answer"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert output["sources"] == []


def test_offline_generator_returns_top_result_text():
    generator = OfflineGenerator()
    output = generator(("question", [_result("Paris is the capital of France.")]))
    assert "Paris is the capital of France." in output["answer"]


def test_offline_generator_sources_map_to_retrieved_results():
    results = [_result("evidence one"), _result("evidence two")]
    generator = OfflineGenerator()
    output = generator(("question", results))
    assert len(output["sources"]) == 2
    assert output["sources"][0]["chunk_id"] == "c1"


def test_offline_generator_initializes_module_state_correctly():
    generator = OfflineGenerator()
    assert hasattr(generator, "_modules")


def test_llm_generator_forward_raises_generator_error_without_api_key(monkeypatch):
    """Calling .forward() directly (bypassing Module.__call__'s
    exception wrapping) surfaces the raw GeneratorError."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    generator = LLMGenerator(provider="openai", model="gpt-4o-mini")
    with pytest.raises(GeneratorError, match="OPENAI_API_KEY"):
        generator.forward(("question", [_result()], "prompt text"))


def test_llm_generator_call_wraps_missing_api_key_as_execution_error(monkeypatch):
    """Calling the Module via __call__ (generator(...)) wraps the same
    failure as ragtorch.ExecutionError, per Module.__call__'s real,
    verified exception-handling contract."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    generator = LLMGenerator(provider="openai", model="gpt-4o-mini")
    with pytest.raises(ExecutionError, match="OPENAI_API_KEY"):
        generator(("question", [_result()], "prompt text"))


@requires_openai
def test_llm_generator_mocked_success(monkeypatch):
    """Mocked OpenAI client -- no real network, no real API key."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    mock_client = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Paris. [1]"))]
    mock_client.chat.completions.create.return_value = mock_completion

    with patch("openai.OpenAI", return_value=mock_client):
        generator = LLMGenerator(provider="openai", model="gpt-4o-mini")
        output = generator.forward(("question", [_result()], "prompt text"))

    assert output["answer"] == "Paris. [1]"
    assert len(output["sources"]) == 1


@requires_openai
def test_llm_generator_provider_failure_raises_generator_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("API is down")

    with patch("openai.OpenAI", return_value=mock_client):
        generator = LLMGenerator(provider="openai", model="gpt-4o-mini")
        with pytest.raises(GeneratorError, match="API is down"):
            generator.forward(("question", [_result()], "prompt text"))


def test_llm_generator_unsupported_provider_raises():
    generator = LLMGenerator(provider="not-a-real-provider", model="x")
    with pytest.raises(GeneratorError, match="unsupported"):
        generator.forward(("question", [_result()], "prompt"))


def test_build_generator_offline_mode():
    class FakeConfig:
        mode = "offline"

    generator = build_generator(FakeConfig())
    assert isinstance(generator, OfflineGenerator)


def test_build_generator_llm_mode():
    class FakeConfig:
        mode = "llm"
        llm_provider = "openai"
        llm_model = "gpt-4o-mini"

    generator = build_generator(FakeConfig())
    assert isinstance(generator, LLMGenerator)


def test_build_generator_unknown_mode_raises():
    class FakeConfig:
        mode = "not-a-real-mode"

    with pytest.raises(ValueError, match="unknown mode"):
        build_generator(FakeConfig())
