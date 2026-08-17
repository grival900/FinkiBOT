from pathlib import Path
from unittest.mock import patch

from backend.scrapers.official_site import subjects
from backend.scrapers.official_site.subjects import parse_subject_html, scrape_subjects

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_subject_html_extracts_title_and_syllabus_content():
    html = (FIXTURES / "official_subject.html").read_text(encoding="utf-8")
    title, content = parse_subject_html(html)

    assert title == "Бази на податоци"
    assert "F23L3W004" in content
    assert "Слободан Калајџиски" in content
    assert "Алгоритми и податочни структури" in content


def test_parse_subject_html_missing_region_returns_empty():
    title, content = parse_subject_html("<html><body>no region here</body></html>")
    assert title == ""
    assert content == ""


def test_scrape_subjects_reads_urls_from_already_indexed_courses():
    fake_urls = ["https://www.finki.ukim.mk/mk/subject/F23L3W004"]

    with (
        patch.object(subjects, "_subject_urls_from_courses", return_value=fake_urls),
        patch.object(subjects, "make_client"),
        patch.object(subjects, "get") as mock_get,
        patch.object(subjects, "parse_subject_html", return_value=("Бази на податоци", "syllabus text")),
    ):
        mock_get.return_value.content = b""
        docs = list(scrape_subjects())

    assert len(docs) == 1
    assert docs[0].url == fake_urls[0]
    assert docs[0].source == "official"
    assert docs[0].type == "course"
