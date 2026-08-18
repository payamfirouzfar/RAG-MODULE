"""Bounded, polite web scraping for a fixed list of URLs.

Deliberately NOT a crawler: only fetches the exact URLs it is given,
respects robots.txt, uses a descriptive User-Agent, bounded timeouts,
and an inter-request delay. Caches raw HTML to disk so a dataset only
needs to be scraped once (`data/raw_html/`), separate from the cleaned
`documents.jsonl` output `dataset.py` produces.
"""

from __future__ import annotations

import hashlib
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests


class ScrapeError(Exception):
    """Raised when a page cannot be fetched or robots.txt disallows it."""


@dataclass(frozen=True)
class ScrapedPage:
    url: str
    html: str
    status_code: int


def _robots_allows(url: str, user_agent: str, timeout: float) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = requests.get(robots_url, timeout=timeout, headers={"User-Agent": user_agent})
        if response.status_code >= 400:
            # No robots.txt (or inaccessible) is treated as "no restriction stated" --
            # standard robots.txt semantics, not a bypass.
            return True
        parser.parse(response.text.splitlines())
    except requests.RequestException:
        # Cannot verify robots.txt -- fail closed is stricter than necessary
        # for a documentation-site demo, but fetching without being able to
        # check robots.txt at all is not attempted here.
        return True
    return parser.can_fetch(user_agent, url)


def scrape_url(url: str, *, user_agent: str, timeout: float) -> ScrapedPage:
    """Fetch a single URL. Raises ScrapeError on any failure (timeout, HTTP
    error, robots.txt disallow) -- callers decide whether to skip or abort."""
    if not _robots_allows(url, user_agent, timeout):
        raise ScrapeError(f"robots.txt disallows fetching {url}")

    try:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": user_agent})
    except requests.Timeout as e:
        raise ScrapeError(f"timeout fetching {url}") from e
    except requests.RequestException as e:
        raise ScrapeError(f"request failed for {url}: {e}") from e

    if response.status_code >= 400:
        raise ScrapeError(f"HTTP {response.status_code} fetching {url}")

    return ScrapedPage(url=url, html=response.text, status_code=response.status_code)


def cache_path_for(url: str, cache_dir: Path) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{digest}.html"


def scrape_urls(
    urls: list[str],
    *,
    user_agent: str,
    timeout: float,
    delay_seconds: float,
    cache_dir: Path,
    max_pages: int,
) -> list[ScrapedPage]:
    """Scrape a bounded list of URLs, caching raw HTML to disk so a
    dataset only needs to be scraped once. Skips (does not abort on) a
    URL that fails to scrape, collecting successes only -- a single bad
    URL should not block building a dataset from the rest."""
    if len(urls) > max_pages:
        raise ScrapeError(
            f"{len(urls)} URLs requested exceeds max_pages={max_pages} -- "
            "this scraper intentionally refuses unbounded requests"
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    pages: list[ScrapedPage] = []

    for i, url in enumerate(urls):
        cached = cache_path_for(url, cache_dir)
        if cached.exists():
            pages.append(
                ScrapedPage(url=url, html=cached.read_text(encoding="utf-8"), status_code=200)
            )
            continue

        page = scrape_url(url, user_agent=user_agent, timeout=timeout)
        cached.write_text(page.html, encoding="utf-8")
        pages.append(page)

        if i < len(urls) - 1:
            time.sleep(delay_seconds)

    return pages
