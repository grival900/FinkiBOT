from backend.scrapers.finki_hub.sessions import parse_session_entry


def test_parse_session_entry_extracts_fields():
    title, content, metadata = parse_session_entry("2025/2026 Јуни", "jun_2025_2026.xlsx")
    assert title == "2025/2026 Јуни"
    assert "jun_2025_2026.xlsx" in content
    assert "assets.finki-hub.com/sessions/jun_2025_2026.xlsx" in content
    assert metadata["filename"] == "jun_2025_2026.xlsx"
    assert metadata["academic_year"] == "2025/2026"
    assert metadata["session_type"] == "Јуни"


def test_parse_session_entry_colloquium():
    title, content, metadata = parse_session_entry(
        "2024/2025 Зимски - Прв Колоквиум", "zimski_kol_1_2024_2025.xlsx"
    )
    assert metadata["academic_year"] == "2024/2025"
    assert metadata["session_type"] == "Зимски - Прв Колоквиум"


def test_parse_session_entry_includes_download_link():
    _, content, _ = parse_session_entry("2024/2025 Јуни", "jun_2024_2025.xlsx")
    assert "Линк за преземање: https://assets.finki-hub.com/sessions/jun_2024_2025.xlsx" in content
