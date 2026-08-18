"""Dataset tests: HTML cleaning, deterministic IDs, save/load round-trip."""

from __future__ import annotations

from pathlib import Path

from src.dataset import Document, clean_html, load_dataset, page_to_document, save_dataset
from src.scraper import ScrapedPage


def test_clean_html_strips_boilerplate():
    html = """
    <html><head><title>My Page</title></head>
    <body>
      <nav>navigation link</nav>
      <header>site header</header>
      <main>Real content here.</main>
      <footer>footer text</footer>
      <script>console.log('x')</script>
    </body></html>
    """
    title, text = clean_html(html)
    assert title == "My Page"
    assert "Real content here." in text
    assert "navigation link" not in text
    assert "site header" not in text
    assert "footer text" not in text
    assert "console.log" not in text


def test_clean_html_normalizes_whitespace():
    html = "<html><body><p>hello    \n\n  world</p></body></html>"
    _, text = clean_html(html)
    assert text == "hello world"


def test_clean_html_empty_input():
    title, text = clean_html("")
    assert title == ""
    assert text == ""


def test_document_id_is_deterministic():
    page1 = ScrapedPage(url="http://example.com/x", html="<html></html>", status_code=200)
    page2 = ScrapedPage(url="http://example.com/x", html="<html>different</html>", status_code=200)
    doc1 = page_to_document(page1, retrieved_at="2026-01-01")
    doc2 = page_to_document(page2, retrieved_at="2026-01-02")
    assert doc1.document_id == doc2.document_id  # same URL -> same ID regardless of content/time


def test_document_id_differs_for_different_urls():
    page1 = ScrapedPage(url="http://example.com/a", html="", status_code=200)
    page2 = ScrapedPage(url="http://example.com/b", html="", status_code=200)
    doc1 = page_to_document(page1)
    doc2 = page_to_document(page2)
    assert doc1.document_id != doc2.document_id


def test_save_and_load_round_trip(tmp_path: Path):
    docs = [
        Document(
            document_id="d1", url="http://a", title="A", text="text a", retrieved_at="2026-01-01"
        ),
        Document(
            document_id="d2", url="http://b", title="B", text="text b", retrieved_at="2026-01-01"
        ),
    ]
    path = tmp_path / "documents.jsonl"
    save_dataset(docs, path)
    loaded = load_dataset(path)
    assert loaded == docs


def test_load_dataset_missing_file_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        load_dataset(Path("/nonexistent/documents.jsonl"))


def test_save_dataset_handles_unicode(tmp_path: Path):
    docs = [
        Document(
            document_id="d1",
            url="http://a",
            title="日本語",
            text="مرحبا 你好 😀",
            retrieved_at="2026-01-01",
        ),
    ]
    path = tmp_path / "documents.jsonl"
    save_dataset(docs, path)
    loaded = load_dataset(path)
    assert loaded[0].title == "日本語"
    assert loaded[0].text == "مرحبا 你好 😀"
