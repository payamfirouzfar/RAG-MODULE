"""Scraper tests: successful page, timeout, HTTP error, malformed HTML,
empty content. All mocked -- no live network access."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from src.scraper import ScrapeError, cache_path_for, scrape_url, scrape_urls

USER_AGENT = "test-agent/1.0"


def _mock_response(status_code: int, text: str = "<html></html>") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@patch("src.scraper.requests.get")
def test_successful_page(mock_get):
    mock_get.side_effect = [
        _mock_response(200, "no robots restriction"),  # robots.txt fetch
        _mock_response(200, "<html><body>hello</body></html>"),
    ]
    page = scrape_url("http://example.com/page", user_agent=USER_AGENT, timeout=5.0)
    assert page.status_code == 200
    assert "hello" in page.html


@patch("src.scraper.requests.get")
def test_timeout_raises_scrape_error(mock_get):
    mock_get.side_effect = [
        _mock_response(200, ""),  # robots.txt fetch succeeds
        requests.Timeout("timed out"),
    ]
    with pytest.raises(ScrapeError, match="timeout"):
        scrape_url("http://example.com/slow", user_agent=USER_AGENT, timeout=1.0)


@patch("src.scraper.requests.get")
def test_http_error_raises_scrape_error(mock_get):
    mock_get.side_effect = [
        _mock_response(200, ""),
        _mock_response(404, "not found"),
    ]
    with pytest.raises(ScrapeError, match="404"):
        scrape_url("http://example.com/missing", user_agent=USER_AGENT, timeout=5.0)


@patch("src.scraper.requests.get")
def test_malformed_html_does_not_raise(mock_get):
    """A scrape itself should succeed even if the HTML is malformed --
    cleaning/parsing failures belong to dataset.clean_html, not the
    scraper."""
    mock_get.side_effect = [
        _mock_response(200, ""),
        _mock_response(200, "<html><body><div>unclosed"),
    ]
    page = scrape_url("http://example.com/broken", user_agent=USER_AGENT, timeout=5.0)
    assert page.status_code == 200


@patch("src.scraper.requests.get")
def test_empty_content(mock_get):
    mock_get.side_effect = [
        _mock_response(200, ""),
        _mock_response(200, ""),
    ]
    page = scrape_url("http://example.com/empty", user_agent=USER_AGENT, timeout=5.0)
    assert page.html == ""


@patch("src.scraper.requests.get")
def test_robots_disallow_raises_scrape_error(mock_get):
    mock_get.side_effect = [
        _mock_response(200, "User-agent: *\nDisallow: /"),
    ]
    with pytest.raises(ScrapeError, match="robots"):
        scrape_url("http://example.com/disallowed", user_agent=USER_AGENT, timeout=5.0)


def test_cache_path_is_deterministic(tmp_path: Path):
    p1 = cache_path_for("http://example.com/x", tmp_path)
    p2 = cache_path_for("http://example.com/x", tmp_path)
    assert p1 == p2


def test_cache_path_differs_for_different_urls(tmp_path: Path):
    p1 = cache_path_for("http://example.com/a", tmp_path)
    p2 = cache_path_for("http://example.com/b", tmp_path)
    assert p1 != p2


@patch("src.scraper.requests.get")
def test_scrape_urls_uses_cache_on_second_call(mock_get, tmp_path: Path):
    mock_get.side_effect = [
        _mock_response(200, ""),
        _mock_response(200, "<html><body>cached content</body></html>"),
    ]
    pages1 = scrape_urls(
        ["http://example.com/cacheme"],
        user_agent=USER_AGENT,
        timeout=5.0,
        delay_seconds=0.0,
        cache_dir=tmp_path,
        max_pages=10,
    )
    assert len(pages1) == 1
    assert mock_get.call_count == 2  # robots.txt + page

    # second call must not hit the network at all -- served from cache
    pages2 = scrape_urls(
        ["http://example.com/cacheme"],
        user_agent=USER_AGENT,
        timeout=5.0,
        delay_seconds=0.0,
        cache_dir=tmp_path,
        max_pages=10,
    )
    assert len(pages2) == 1
    assert mock_get.call_count == 2  # unchanged


def test_scrape_urls_refuses_to_exceed_max_pages(tmp_path: Path):
    with pytest.raises(ScrapeError, match="max_pages"):
        scrape_urls(
            ["http://a", "http://b", "http://c"],
            user_agent=USER_AGENT,
            timeout=5.0,
            delay_seconds=0.0,
            cache_dir=tmp_path,
            max_pages=2,
        )
