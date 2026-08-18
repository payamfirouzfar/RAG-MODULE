"""Deterministic, character-based chunking with configurable size/overlap.

No hard-coded chunk_size/chunk_overlap anywhere -- both are parameters,
sourced from Config in real use.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .dataset import Document


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    url: str
    title: str
    text: str
    chunk_index: int

    def to_dict(self) -> dict:
        return asdict(self)


def chunk_document(document: Document, *, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Split document.text into overlapping character windows.

    Deterministic: the same document + same (chunk_size, chunk_overlap)
    always produces the same chunks with the same chunk_ids, across runs.
    An empty document produces zero chunks (not an error, not a single
    empty chunk).
    """
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be smaller than chunk_size ({chunk_size})"
        )

    text = document.text
    if not text:
        return []

    step = chunk_size - chunk_overlap
    chunks: list[Chunk] = []
    index = 0
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end]
        chunks.append(
            Chunk(
                chunk_id=f"{document.document_id}::{index}",
                document_id=document.document_id,
                url=document.url,
                title=document.title,
                text=piece,
                chunk_index=index,
            )
        )
        index += 1
        if end == len(text):
            break
        start += step

    return chunks


def chunk_documents(
    documents: list[Document], *, chunk_size: int, chunk_overlap: int
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
    return chunks
