"""Single configuration object for the entire demo application.

Every tunable value (embedding model, chunk size, top-k, mode, ...) is
read from this one place, never scattered through the notebook or the
other modules. Change behavior by editing CONFIG, not by editing
application internals.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # --- Dataset ---
    urls: list[str] = field(default_factory=list)
    dataset_path: str = "data/documents.jsonl"
    scrape_timeout_seconds: float = 10.0
    scrape_user_agent: str = (
        "ragmodel-rag-consumer-demo/0.1 "
        "(+https://github.com/payamfirouzfar/RAG-MODULE; educational RAG demo)"
    )
    scrape_delay_seconds: float = 1.0
    max_pages: int = 20

    # --- Chunking ---
    chunk_size: int = 800
    chunk_overlap: int = 120

    # --- Embeddings ---
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Vector store ---
    vector_store_backend: str = "faiss"  # "faiss" or "in_memory"
    vector_store_path: str = "data/vector_store"

    # --- Retrieval ---
    top_k: int = 5
    min_score: float | None = 0.2
    rerank: bool = False

    # --- Generation ---
    mode: str = "offline"  # "offline" or "llm"
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    llm_model: str = "gpt-4o-mini"

    def __post_init__(self) -> None:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be smaller than "
                f"chunk_size ({self.chunk_size})"
            )
        if self.mode not in ("offline", "llm"):
            raise ValueError(f"mode must be 'offline' or 'llm', got {self.mode!r}")
        if self.top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {self.top_k}")


DEFAULT_CONFIG = Config(
    urls=[
        "https://docs.python.org/3/tutorial/introduction.html",
        "https://docs.python.org/3/tutorial/controlflow.html",
        "https://docs.python.org/3/tutorial/datastructures.html",
        "https://docs.python.org/3/tutorial/modules.html",
        "https://docs.python.org/3/tutorial/errors.html",
    ]
)
