"""HTML cleaning, deterministic document IDs, and documents.jsonl
save/load.

Supports two modes:
- SCRAPE MODE: build_dataset() fetches pages via scraper.py, cleans and
  saves them.
- OFFLINE DATASET MODE: load_dataset() reads an already-saved
  documents.jsonl without touching the network at all.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from .scraper import ScrapedPage, scrape_urls

_BOILERPLATE_TAGS = ("nav", "header", "footer", "script", "style", "aside", "noscript")


@dataclass(frozen=True)
class Document:
    document_id: str
    url: str
    title: str
    text: str
    retrieved_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Document:
        return cls(**data)


def _document_id_for(url: str) -> str:
    """Deterministic document ID: same URL always produces the same ID,
    across runs and machines, without depending on scrape order."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def clean_html(html: str) -> tuple[str, str]:
    """Return (title, cleaned_text). Strips navigation/script/style/etc.,
    normalizes whitespace. Returns ("", "") for HTML with no extractable
    text content rather than raising."""
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in _BOILERPLATE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    raw_text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", raw_text).strip()

    return title, text


def page_to_document(page: ScrapedPage, *, retrieved_at: str | None = None) -> Document:
    title, text = clean_html(page.html)
    return Document(
        document_id=_document_id_for(page.url),
        url=page.url,
        title=title,
        text=text,
        retrieved_at=retrieved_at or datetime.now(UTC).isoformat(),
    )


def build_dataset(
    urls: list[str],
    *,
    user_agent: str,
    timeout: float,
    delay_seconds: float,
    cache_dir: Path,
    max_pages: int,
) -> list[Document]:
    """SCRAPE MODE: fetch pages (network + local HTML cache) and return
    cleaned Documents. Does not save to documents.jsonl itself -- call
    save_dataset() separately so scraping and persistence stay
    independently testable."""
    pages = scrape_urls(
        urls,
        user_agent=user_agent,
        timeout=timeout,
        delay_seconds=delay_seconds,
        cache_dir=cache_dir,
        max_pages=max_pages,
    )
    return [page_to_document(page) for page in pages]


def save_dataset(documents: list[Document], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")


def load_dataset(path: Path) -> list[Document]:
    """OFFLINE DATASET MODE: read documents.jsonl with zero network
    access. Raises FileNotFoundError if the dataset was never built --
    callers should catch this and fall back to build_dataset()."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist -- run build_dataset()+save_dataset() first, "
            "or switch to a directory that already has a saved dataset"
        )
    documents = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            documents.append(Document.from_dict(json.loads(line)))
    return documents
