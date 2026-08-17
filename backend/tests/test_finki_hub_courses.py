from pathlib import Path

from backend.scrapers.finki_hub.courses import _format_content, parse_dialog_html

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_dialog_html_extracts_professors_and_assistants():
    html = (FIXTURES / "finki_hub_course_dialog.html").read_text(encoding="utf-8")
    details = parse_dialog_html(html)

    assert details["professors"] == ["Марјан Гушев"]
    assert details["assistants"] == ["Ана Мадевска Богданова"]


def test_parse_dialog_html_extracts_accreditation_card_fields():
    html = (FIXTURES / "finki_hub_course_dialog.html").read_text(encoding="utf-8")
    details = parse_dialog_html(html)

    assert len(details["accreditations"]) == 1
    acc = details["accreditations"][0]
    assert acc["year"] == "2023"
    assert acc["official_url"] == "https://www.finki.ukim.mk/mk/subject/F23L3S139"
    assert acc["Код"] == "F23L3S139"
    assert acc["Ниво"] == "3"
    assert acc["Семестар"] == "8"
    assert acc["Предуслов"] == "Алгоритми и податочни структури"


def test_format_content_includes_level_prerequisite_and_staff():
    html = (FIXTURES / "finki_hub_course_dialog.html").read_text(encoding="utf-8")
    details = parse_dialog_html(html)

    content = _format_content("Web3 апликации", ["Веб"], details)

    assert "Ниво: 3, Семестар: 8" in content
    assert "Предуслов: Алгоритми и податочни структури" in content
    assert "Професори: Марјан Гушев" in content
    assert "Асистенти: Ана Мадевска Богданова" in content
    assert "Тагови: Веб" in content
    assert "Акредитации: 2023" in content


def test_parse_dialog_html_missing_dialog_returns_empty():
    details = parse_dialog_html("<div>no dialog content</div>")
    assert details == {"professors": [], "assistants": [], "accreditations": []}
