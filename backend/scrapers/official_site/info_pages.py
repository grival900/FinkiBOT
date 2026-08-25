"""Scrapes static informational pages from finki.ukim.mk — About Us (faculty
overview, leadership, institutes/labs, partnerships), Studies (programs, student
services, academic calendar), Admissions (quotas, requirements, documents per study
cycle), International Students, and Contact.

Discovered by hand-walking the site's own nav menu, not a sitemap or any other
automated discovery: every `/wp-sitemap*` path on finki.ukim.mk 307-redirects to a
decommissioned domain (see `professors.py`'s docstring) — the same dead end that got
the original `official.pages` scraper removed. `PAGE_URLS` below is that hand-curated
list; there is no listing endpoint to keep it in sync automatically, so a genuinely
new page here means manually adding its URL.

Deliberately excludes:
  - Legal/procurement/finance/reports pages (low relevance for a student-facing
    assistant, and legal text is exactly the kind of content that goes stale
    silently and is worst to get wrong).
  - English (`/en/...`) versions — several redirect straight back to the Macedonian
    page rather than serving real translated content, and the embedding model is
    multilingual, so an English question still retrieves the Macedonian source fine.
  - PDF-only content (org chart, international-student guide) and external sites
    (career center, alumni, cybermacs.eu) — out of scope for this HTML scraper.
  - Pure "hub" pages that are nothing but link-cards to deeper pages (e.g.
    `/upisi/dodiplomski-studii/` itself) — their linked leaf pages are listed here
    directly instead, so nothing real is lost, and no near-empty stub gets indexed.

Confirmed live: unlike announcements/professors, this content does *not* share one
template — `extract_info_page_text` (see `base.py`) tries several selectors in
priority order. `MIN_CONTENT_LENGTH` is a safety net for any URL here that turns out
to still be more of a stub than expected.
"""

import logging
from collections.abc import Iterator

import httpx

from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import BASE_URL, extract_info_page_text, parse_html

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 80

PAGE_URLS = [
    # About Us
    "/za-nas/nastavno-nauchna-dejnost/za-fakultetot/",
    "/za-nas/rakovodstvo-i-organizacija/dekanat/",
    "/za-nas/rakovodstvo-i-organizacija/dekanatska-uprava/",
    "/za-nas/rakovodstvo-i-organizacija/nastavno-nauchen-sovet/",
    "/za-nas/rakovodstvo-i-organizacija/instituti-i-centri/",
    "/za-nas/rakovodstvo-i-organizacija/laboratorii/",
    "/za-nas/administracija-i-dokumenti/partnerstva/",
    "/za-nas/nastavno-nauchna-dejnost/finki-e-moj-izbor/",
    # Studies
    "/studii-2/vidovi-studii/",
    "/studii-2/vidovi-studii/dodiplomski-studii/",
    "/studii-2/vidovi-studii/magisterski-studii-2/",
    "/studii-2/vidovi-studii/doktorski-studii/",
    "/studii-2/poddrshka/studentska-sluzhba/",
    "/studii-2/poddrshka/dokumenti-i-proceduri/",
    "/studii-2/poddrshka/obrasci/",
    "/studii-2/poddrshka/erazmus/",
    "/studii-2/akademski-resursi-i-raspored/raspored-na-ispiti/",
    "/studii-2/akademski-resursi-i-raspored/akademski-kalendar/",
    "/studii-2/akademski-resursi-i-raspored/reshenija/",
    "/studii-2/zavrshni-obvrski-i-odbrani/odbrani/",
    # Admissions — undergraduate
    "/upisi/dodiplomski-studii/kvoti/",
    "/upisi/dodiplomski-studii/potrebni-dokumenti/",
    "/upisi/dodiplomski-studii/izbor-na-studiska-programa/",
    "/upisi/dodiplomski-studii/potrebni-predmeti/",
    "/upisi/dodiplomski-studii/presmetuvanje-na-bodovi/",
    "/upisi/dodiplomski-studii/stipendii/",
    # Admissions — master's
    "/upisi/magisterski-studii/kvoti/",
    "/upisi/magisterski-studii/potrebni-dokumenti/",
    "/upisi/magisterski-studii/uslovi/",
    # Admissions — PhD
    "/upisi/doktorski-studii/kvoti/",
    "/upisi/doktorski-studii/potrebni-dokumenti/",
    "/upisi/doktorski-studii/uslovi/",
    "/upisi/doktorski-studii/akreditirani-mentori/",
    # International Students
    "/internacionalni-studenti/admissions/undergraduate-studies-for-international-students/",
    "/internacionalni-studenti/admissions/masters-studies-for-international-students/",
    # Contact
    "/kontakt/",
]


def parse_info_page_html(html: bytes | str) -> tuple[str, str]:
    """Pure parsing step, unit-testable against a saved fixture. Returns (title, content_text)."""
    soup = parse_html(html)
    h1 = soup.select_one("h1")
    title = h1.get_text(strip=True) if h1 else ""
    return title, extract_info_page_text(soup)


def scrape_info_pages() -> Iterator[NormalizedDocument]:
    with make_client() as client:
        for path in PAGE_URLS:
            url = f"{BASE_URL}{path}"
            try:
                response = get(client, url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch info page: %s", url)
                continue

            title, content = parse_info_page_html(response.content)
            if len(content) < MIN_CONTENT_LENGTH:
                logger.warning("Skipping near-empty info page (%d chars): %s", len(content), url)
                continue

            yield NormalizedDocument(
                source="official",
                type="page",
                title=title or url,
                url=url,
                content=content,
            ).clean()
