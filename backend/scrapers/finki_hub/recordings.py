"""Scrapes snimki.finki-hub.com — a community-maintained (unofficial) collection of
recorded-lecture links, playlists, and notes, one static page per course. Confirmed
live: server-rendered (VitePress), course pages are linked from the `/introduction.html`
sidebar (68 confirmed live) — no separate sitemap exists.

Each course page lists recording links grouped by professor/year/lecture, plus
"Дополнителна содржина" (additional content) and "Белешки" (notes) sections when
filled in. This is what finki-hub actually has under the "materials" umbrella — there
is no separate slides/notes repository distinct from this recordings+notes collection,
confirmed by checking finki-hub.com's own platform list live.

Content is captured as markdown, not flattened plain text: every recording is an
`<a href>` to its actual playback URL (bbb-lb.finki.ukim.mk), and losing those hrefs
(the old behavior — `get_text()` keeps only the visible label, e.g. "Предавање 1")
would mean the frontend's internal document page has no way to link to the actual
recording, only to the finki-hub course page as a whole. `_to_markdown` preserves
each link as `[label](href)` instead so they render clickable wherever this content is
shown (see `documents.$id.tsx`), and keeps subheadings (`## `/`### `) so the
professor/year/lecture grouping survives too.
"""

import logging
from collections.abc import Iterator
from urllib.parse import urljoin

import httpx
from bs4 import Tag

from backend.scrapers.finki_hub.base import SNIMKI_URL, parse_html
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)

INTRODUCTION_PATH = "/introduction.html"


def parse_course_links(html: bytes | str) -> list[str]:
    """Pure parsing step, unit-testable against a saved fixture. Returns absolute course-page URLs."""
    soup = parse_html(html)
    urls = {urljoin(SNIMKI_URL, a["href"]) for a in soup.select('a[href*="/courses/"]')}
    return sorted(urls)


def _to_markdown(root: Tag) -> str:
    lines: list[str] = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "li", "p"]):
        if el.name in ("h1", "h2", "h3", "h4"):
            anchor = el.select_one(".header-anchor")
            if anchor is not None:
                anchor.decompose()  # VitePress's zero-width-space deep-link marker
            text = el.get_text(strip=True)
            if not text:
                continue
            # h1 duplicates the title, but must still go into the *content* — only
            # content gets chunked/embedded (see ingestion/pipeline.py), never title,
            # so dropping it here meant the course name itself was invisible to
            # search: querying a course by name matched nothing, since the returned
            # content started at "## Предавања" with no mention of the course at all.
            lines.append(f"{'#' * int(el.name[1])} {text}")
            continue

        link = el.find("a", href=True)
        if link is not None:
            label = link.get_text(strip=True)
            if label:
                lines.append(f"- [{label}]({link['href']})")
            continue

        text = el.get_text(strip=True)
        if text:
            lines.append(f"- {text}" if el.name == "li" else text)
    return "\n".join(lines)


def parse_course_page_html(html: bytes | str) -> tuple[str, str]:
    """Pure parsing step. Returns (title, content_markdown)."""
    soup = parse_html(html)
    main_el = soup.select_one(".vp-doc")
    if main_el is None:
        return "", ""
    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True).replace("​", "") if title_el else ""
    return title, _to_markdown(main_el)


def scrape_recordings() -> Iterator[NormalizedDocument]:
    with make_client() as client:
        intro_response = get(client, f"{SNIMKI_URL}{INTRODUCTION_PATH}")
        urls = parse_course_links(intro_response.content)

        for url in urls:
            try:
                response = get(client, url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch recordings page: %s", url)
                continue

            title, content = parse_course_page_html(response.content)
            if not content:
                continue

            yield NormalizedDocument(
                source="finki_hub",
                type="material",
                title=title or url,
                url=url,
                content=content,
            ).clean()
