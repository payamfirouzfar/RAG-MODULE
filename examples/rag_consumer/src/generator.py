"""Generator(Module): produces {"answer": ..., "sources": [...]}.

Two modes:
- OfflineGenerator: deterministic extractive answer, no API key, no
  network. Used when CONFIG["mode"] == "offline" or no LLM API key is
  configured.
- LLMGenerator: real LLM call via a provider configured through an
  environment variable (never hardcoded, never in notebook source).

Both are Module subclasses satisfying the same forward(payload) ->
{"answer", "sources"} contract, so pipeline.py can swap between them
without any other component changing.
"""

from __future__ import annotations

import os

from ragtorch import Module

from .prompt_builder import SYSTEM_INSTRUCTIONS
from .retriever import RetrievalResult

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "The available evidence is insufficient to answer this question confidently."
)


class GeneratorError(Exception):
    """Raised when generation fails (e.g. missing API key, provider
    error) -- never silently swallowed; the pipeline decides whether to
    propagate or handle it."""


def _sources_from(results: list[RetrievalResult]) -> list[dict]:
    """Every citation must map to something that was actually retrieved
    -- this is the ONLY place source objects are constructed, from the
    real RetrievalResult list, never invented."""
    return [
        {"index": i + 1, "title": r.title, "url": r.url, "chunk_id": r.chunk_id}
        for i, r in enumerate(results)
    ]


class OfflineGenerator(Module):
    """Deterministic extractive generator: no LLM, no API key, no
    network. Returns the single highest-scored retrieved chunk's text
    as the answer (with a citation), or the insufficient-evidence
    message if nothing was retrieved. This is what MODE="offline" uses,
    and what every notebook run works with even without any API key."""

    def forward(self, payload: tuple[str, list[RetrievalResult]], *, context=None) -> dict:
        _question, results = payload
        if not results:
            return {"answer": INSUFFICIENT_EVIDENCE_MESSAGE, "sources": []}

        top = results[0]
        answer = f"{top.text.strip()} [1]"
        return {"answer": answer, "sources": _sources_from(results)}


class LLMGenerator(Module):
    """Real LLM-backed generator. Provider selected via the
    LLM_PROVIDER environment variable (default "openai"); the API key
    is read from the provider's own standard environment variable
    (e.g. OPENAI_API_KEY) or Colab Secrets -- never from source code or
    a notebook cell. Raises GeneratorError (not a silent fallback) if
    no API key is configured, so callers can decide to fall back to
    OfflineGenerator explicitly rather than have failures hidden."""

    def __init__(self, *, provider: str, model: str) -> None:
        super().__init__()
        self._provider = provider
        self._model = model

    def forward(self, payload: tuple[str, list[RetrievalResult], str], *, context=None) -> dict:
        question, results, prompt = payload

        if self._provider == "openai":
            answer_text = self._call_openai(prompt)
        else:
            raise GeneratorError(f"unsupported LLM_PROVIDER: {self._provider!r}")

        return {"answer": answer_text, "sources": _sources_from(results)}

    def _call_openai(self, prompt: str) -> str:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise GeneratorError(
                "OPENAI_API_KEY is not set. Set it as an environment variable or "
                "a Colab Secret before using MODE='llm' with LLM_PROVIDER='openai'."
            )
        try:
            from openai import OpenAI
        except ImportError as e:
            raise GeneratorError(
                "the openai package is required for LLM_PROVIDER='openai'. "
                "Install it with: pip install openai"
            ) from e

        client = OpenAI(api_key=api_key)
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as e:  # provider SDK exception types vary; never swallow
            raise GeneratorError(f"OpenAI API call failed: {e}") from e

        return response.choices[0].message.content or ""


def build_generator(config) -> Module:
    if config.mode == "offline":
        return OfflineGenerator()
    if config.mode == "llm":
        return LLMGenerator(provider=config.llm_provider, model=config.llm_model)
    raise ValueError(f"unknown mode: {config.mode!r}")
