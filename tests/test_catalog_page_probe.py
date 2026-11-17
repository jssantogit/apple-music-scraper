"""Offline contract for investigating page overlap without leaking raw payloads."""

from scripts import catalog_page_probe as probe


def test_overlap_diagnostic_includes_only_public_ids_and_real_page_boundaries():
    first = [{"id": "11", "attributes": {"name": "A"}},
             {"id": "22", "attributes": {"name": "B"}}]
    second = [{"id": "22", "attributes": {"name": "B"}},
              {"id": "33", "attributes": {"name": "C"}}]

    result = probe.inspect_pair(first, second)

    assert result == {
        "page1_ids": ["11", "22"],
        "page2_ids": ["22", "33"],
        "overlap_ids": ["22"],
        "page1_count": 2,
        "page2_count": 2,
    }
    assert "attributes" not in repr(result)


def test_overlap_diagnostic_distinguishes_valid_disjoint_pages():
    result = probe.inspect_pair([{"id": "11"}], [{"id": "44"}])
    assert result["overlap_ids"] == []


def test_authoritative_next_cursor_parser_accepts_apple_catalog_only():
    path, query = probe.parse_next_cursor(
        "/v1/catalog/in/search?term=Yo-Yo+Ma&types=songs&limit=5&offset=6",
        country="in",
    )
    assert path == "/v1/catalog/in/search"
    assert query["offset"] == "6"
    assert query["term"] == "Yo-Yo Ma"


def test_authoritative_next_cursor_rejects_other_host_or_storefront():
    import pytest
    with pytest.raises(ValueError, match="cursor"):
        probe.parse_next_cursor(
            "https://example.com/v1/catalog/in/search?offset=6",
            country="in",
        )
    with pytest.raises(ValueError, match="cursor"):
        probe.parse_next_cursor(
            "/v1/catalog/us/search?offset=6", country="in",
        )
