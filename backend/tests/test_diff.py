from dataclasses import dataclass

from backend.notifier.diff import matches_filters


@dataclass
class FakeDoc:
    title: str
    content: str


def test_empty_filters_match_everything():
    doc = FakeDoc(title="Наслов", content="содржина")
    assert matches_filters(doc, {}) is True


def test_keyword_match_is_case_insensitive_substring():
    doc = FakeDoc(title="Распоред за јунска ИСПИТНА сесија", content="...")
    assert matches_filters(doc, {"keywords": ["испитна сесија"]}) is True


def test_keyword_miss():
    doc = FakeDoc(title="Нешто сосема друго", content="...")
    assert matches_filters(doc, {"keywords": ["запишување"]}) is False


def test_course_code_matched_like_a_keyword():
    doc = FakeDoc(title="Промена на термин", content="важи за F23L3S139")
    assert matches_filters(doc, {"course_codes": ["F23L3S139"]}) is True
