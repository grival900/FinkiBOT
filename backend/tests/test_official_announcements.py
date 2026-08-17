from pathlib import Path
from unittest.mock import patch

from backend.core.config import Settings
from backend.scrapers.official_site import announcements
from backend.scrapers.official_site.announcements import parse_detail_html, parse_listing_html, scrape_announcements
from backend.scrapers.official_site.base import parse_drupal_date

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_listing_html_extracts_title_url_and_date():
    html = (FIXTURES / "announcement_listing.html").read_text(encoding="utf-8")
    rows = parse_listing_html(html)

    assert len(rows) == 2
    title, url, date_text = rows[0]
    assert title == "Запишување нови студенти во учебната 2026/2027 година"
    assert url.endswith("/mk/content/zapishuvanje-novi-studenti-0")
    assert date_text == "20.07.2026"


def test_parse_detail_html_extracts_content_and_date():
    html = (FIXTURES / "announcement_detail.html").read_text(encoding="utf-8")
    content, date_text = parse_detail_html(html)

    assert "Ве известуваме" in content
    assert date_text == "20/07/2026"


def test_parse_drupal_date_handles_both_listing_and_detail_formats():
    assert parse_drupal_date("20.07.2026").isoformat() == "2026-07-20T00:00:00"
    assert parse_drupal_date("20/07/2026").isoformat() == "2026-07-20T00:00:00"
    assert parse_drupal_date("not a date") is None


def test_scrape_announcements_stops_at_the_configured_limit():
    """The listing is newest-first, so a limit caps this to the N most recent
    announcements — verified here against a fake 5-row listing, no live network."""
    fake_rows = [(f"Title {i}", f"https://finki.ukim.mk/mk/content/item-{i}", "01.01.2026") for i in range(5)]

    with (
        patch.object(announcements, "_iter_listing_rows", return_value=iter(fake_rows)),
        patch.object(announcements, "_fetch_detail", return_value=("body text", "01/01/2026")),
        patch.object(announcements, "make_client"),
        patch.object(announcements, "get_settings", return_value=Settings(scrape_announcement_limit=2)),
    ):
        docs = list(scrape_announcements())

    assert [d.title for d in docs] == ["Title 0", "Title 1"]


def test_scrape_announcements_unlimited_by_default():
    fake_rows = [(f"Title {i}", f"https://finki.ukim.mk/mk/content/item-{i}", "01.01.2026") for i in range(5)]

    with (
        patch.object(announcements, "_iter_listing_rows", return_value=iter(fake_rows)),
        patch.object(announcements, "_fetch_detail", return_value=("body text", "01/01/2026")),
        patch.object(announcements, "make_client"),
        patch.object(announcements, "get_settings", return_value=Settings(scrape_announcement_limit=None)),
    ):
        docs = list(scrape_announcements())

    assert len(docs) == 5
