from pathlib import Path
from unittest.mock import patch

from backend.scrapers.official_site import pages
from backend.scrapers.official_site.pages import parse_page_html, parse_sitemap_xml, scrape_pages

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_sitemap_xml_extracts_urls():
    xml = (FIXTURES / "pages_sitemap.xml").read_text(encoding="utf-8")
    urls = parse_sitemap_xml(xml)

    assert urls == [
        "https://finki.ukim.mk/studii-2/poddrshka/studentska-sluzhba/",
        "https://finki.ukim.mk/za-nas/",
    ]


def test_parse_page_html_extracts_title_and_content_without_share_widget():
    html = (FIXTURES / "official_page.html").read_text(encoding="utf-8")
    title, content = parse_page_html(html)

    assert title == "Студентска служба"
    assert "09:00" in content
    assert "studentski@finki.ukim.mk" in content
    assert "Facebook" not in content


def test_scrape_pages_yields_one_document_per_sitemap_url():
    fake_urls = ["https://finki.ukim.mk/page-a/", "https://finki.ukim.mk/page-b/"]
    body_a = "Body A " * 20
    body_b = "Body B " * 20

    with (
        patch.object(pages, "make_client"),
        patch.object(pages, "get") as mock_get,
        patch.object(pages, "parse_sitemap_xml", return_value=fake_urls),
        patch.object(pages, "parse_page_html", side_effect=[("Title A", body_a), ("Title B", body_b)]),
    ):
        mock_get.return_value.content = b""
        mock_get.return_value.url.path = "/page-a/"
        docs = list(scrape_pages())

    assert [d.url for d in docs] == fake_urls
    assert [d.title for d in docs] == ["Title A", "Title B"]
    assert all(d.type == "page" for d in docs)


def test_scrape_pages_skips_near_empty_landing_pages():
    """Section-landing pages whose body is just the title repeated (or a couple of nav
    labels) embed as generic, deceptively high-scoring noise — must be filtered out."""
    fake_urls = ["https://finki.ukim.mk/studii-2/", "https://finki.ukim.mk/page-b/"]

    with (
        patch.object(pages, "make_client"),
        patch.object(pages, "get") as mock_get,
        patch.object(pages, "parse_sitemap_xml", return_value=fake_urls),
        patch.object(pages, "parse_page_html", side_effect=[("Студии", "Студии"), ("Title B", "Body B " * 20)]),
    ):
        mock_get.return_value.content = b""
        mock_get.return_value.url.path = "/studii-2/"
        docs = list(scrape_pages())

    assert [d.url for d in docs] == ["https://finki.ukim.mk/page-b/"]


def test_scrape_pages_skips_soft_404_redirects():
    """Stale sitemap entries redirect to /not-found/, which itself responds 200 OK —
    must be detected via the landed URL, not the (successful) status code."""
    fake_urls = ["https://finki.ukim.mk/gone/", "https://finki.ukim.mk/page-b/"]

    with (
        patch.object(pages, "make_client"),
        patch.object(pages, "get") as mock_get,
        patch.object(pages, "parse_sitemap_xml", return_value=fake_urls),
        patch.object(pages, "parse_page_html", return_value=("Title B", "Body B " * 20)),
    ):
        mock_get.side_effect = [
            type("R", (), {"content": b""})(),  # sitemap fetch itself
            type("R", (), {"content": b"", "url": type("U", (), {"path": "/not-found/"})()})(),
            type("R", (), {"content": b"", "url": type("U", (), {"path": "/page-b/"})()})(),
        ]
        docs = list(scrape_pages())

    assert [d.url for d in docs] == ["https://finki.ukim.mk/page-b/"]
