from backend.core.insights import count_semesters, count_tags


def test_count_tags_ranks_by_frequency():
    metadata_list = [
        {"tags": ["Бази на податоци"]},
        {"tags": ["Бази на податоци", "Веб"]},
        {"tags": ["Веб"]},
        {"tags": []},
    ]
    assert count_tags(metadata_list) == [
        {"tag": "Бази на податоци", "count": 2},
        {"tag": "Веб", "count": 2},
    ]


def test_count_tags_respects_limit():
    metadata_list = [{"tags": [f"tag{i}"]} for i in range(20)]
    assert len(count_tags(metadata_list, limit=5)) == 5


def test_count_semesters_uses_most_recent_accreditation_only():
    metadata_list = [
        {"accreditations": [{"Семестар": "5"}, {"Семестар": "3"}]},  # only "5" counted
        {"accreditations": [{"Семестар": "5"}]},
        {"accreditations": [{"Семестар": "1"}]},
        {"accreditations": []},  # no accreditations, skipped
        {},  # missing key entirely, skipped
    ]
    assert count_semesters(metadata_list) == [
        {"semester": "1", "count": 1},
        {"semester": "5", "count": 2},
    ]


def test_count_semesters_sorts_numerically_not_lexically():
    """Lexical sort would put "10" before "2" — must sort numerically."""
    metadata_list = [
        {"accreditations": [{"Семестар": "10"}]},
        {"accreditations": [{"Семестар": "2"}]},
    ]
    assert [s["semester"] for s in count_semesters(metadata_list)] == ["2", "10"]
