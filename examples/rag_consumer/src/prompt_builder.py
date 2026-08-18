"""PromptBuilder: a separate application component, not buried inside
the generator. Input: question + retrieved context. Output: a prompt
string with explicit instructions to use only the retrieved evidence,
never invent facts, say so when evidence is insufficient, and cite
sources."""

from __future__ import annotations

from .retriever import RetrievalResult

SYSTEM_INSTRUCTIONS = (
    "You are a retrieval-augmented assistant. Answer the question using ONLY "
    "the retrieved evidence provided below. Do not invent facts that are not "
    "supported by the evidence. If the evidence does not contain enough "
    "information to answer the question, say explicitly that the available "
    "evidence is insufficient -- do not guess. When you answer, cite the "
    "source number(s) (e.g. [1], [2]) for every claim you make."
)


def build_prompt(question: str, results: list[RetrievalResult]) -> str:
    if not results:
        context_block = "(no evidence was retrieved for this question)"
    else:
        context_block = "\n\n".join(
            f"[{i + 1}] (source: {r.title or r.url})\n{r.text}" for i, r in enumerate(results)
        )

    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"Retrieved evidence:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Answer (with citations):"
    )
