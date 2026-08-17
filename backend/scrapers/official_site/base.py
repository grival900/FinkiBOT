from bs4 import BeautifulSoup, Tag

BASE_URL = "https://finki.ukim.mk"


def element_to_text(el: Tag) -> str:
    text = el.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_html(content: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(content, "lxml")


def parse_xml(content: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(content, "xml")


def extract_page_body_text(soup: BeautifulSoup) -> str:
    """Shared by both `announcements.py` and `pages.py` — both are WordPress single-page
    views sharing the same `.page-content__body` template, which injects an AddToAny
    share-button widget (`.addtoany_share_save_container`) at the top that isn't part of
    the actual page content and must be stripped before extracting text."""
    body_el = soup.select_one(".page-content__body")
    if body_el is None:
        return ""
    share_widget = body_el.select_one(".addtoany_share_save_container")
    if share_widget is not None:
        share_widget.decompose()
    return element_to_text(body_el)
