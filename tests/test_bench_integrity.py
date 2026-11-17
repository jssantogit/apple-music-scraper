"""Regression tests preventing false-green cross-storefront and pagination results.

All tests are offline: payloads are synthetic and the real application is never
allowed to contact Apple's catalog.
"""
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import catalog_bench as bench


def _search_page(*, page=1, limit=2, ids=("a", "b"), next_url=None, per_page=None):
    return {
        "query": "jazz",
        "songs": [{"id": identity, "name": identity} for identity in ids],
        "current_page": page,
        "per_page": per_page if per_page is not None else limit,
        "total_pages": 2,
        "next": next_url,
        "previous": None if page == 1 else "http://localhost/search/songs?page=1",
    }


def test_coverage_cannot_pass_with_missing_endpoint_in_second_country():
    rows = [
        {"country": "br", "path": "/songs/details", "result": "pass"},
        {"country": "br", "path": "/artists/details", "result": "pass"},
        {"country": "us", "path": "/songs/details", "result": "pass"},
    ]
    result = bench.summarize(
        rows,
        expected_routes={"/songs/details", "/artists/details"},
        expected_countries={"br", "us"},
    )
    assert result["passed"] is False
    assert result["missing_cases"] == ["us:/artists/details"]
    assert result["covered_cases"] == 3
    assert result["total_cases_expected"] == 4


def test_pagination_rejects_wrong_limit_even_with_http_200():
    payload = _search_page(per_page=100)
    checked = bench.validate_result(
        "/search/songs", 200, payload, {"page": "1", "limit": "2"},
    )
    assert checked["result"] == "fail"
    assert "per_page" in checked["reason"]


def test_pagination_rejects_more_items_than_requested():
    payload = _search_page(ids=("a", "b", "c"))
    checked = bench.validate_result(
        "/search/songs", 200, payload, {"page": "1", "limit": "2"},
    )
    assert checked["result"] == "fail"
    assert "limit" in checked["reason"]


def test_pagination_detects_skipped_next_page():
    payload = _search_page(
        next_url="http://localhost/search/songs?query=jazz&limit=2&page=3"
    )
    checked = bench.validate_result(
        "/search/songs", 200, payload, {"page": "1", "limit": "2", "query": "jazz"},
    )
    assert checked["result"] == "fail"
    assert "next" in checked["reason"]


def test_followup_reuses_real_cursor_and_keeps_country():
    payload = _search_page(
        next_url="http://localhost/search/songs?query=jazz&country=br&limit=2&page=2"
    )
    params = {"page": "1", "limit": "2", "query": "jazz", "country": "br"}
    next_case = bench.followup_case("/search/songs", params, payload)
    assert next_case == {**params, "page": "2"}
    assert bench.followup_case("/search/songs", params, _search_page()) is None


def test_followup_rejects_cross_route_or_country_cursor():
    params = {"page": "1", "limit": "2", "query": "jazz", "country": "br"}
    cross = _search_page(
        next_url="http://localhost/search/artists?query=jazz&country=us&limit=2&page=2"
    )
    with pytest.raises(ValueError, match="cursor"):
        bench.followup_case("/search/songs", params, cross)


def test_followup_detects_repeated_search_song_ids_across_pages():
    first = _search_page(
        ids=("a", "b"),
        next_url="http://localhost/search/songs?query=jazz&limit=2&page=2",
    )
    second = _search_page(page=2, ids=("b", "c"))
    check = bench.compare_pages("/search/songs", first, second)
    assert check["result"] == "fail"
    assert "duplicate" in check["reason"]


def test_followup_allows_disjoint_pages():
    first = _search_page(ids=("a", "b"))
    second = _search_page(page=2, ids=("c", "d"))
    assert bench.compare_pages("/search/songs", first, second)["result"] == "pass"


def test_deep_runner_checks_second_page_and_fails_on_repeated_result(monkeypatch):
    calls = []

    def fake_transport(path, params):
        calls.append((path, dict(params)))
        if params["page"] == "1":
            return 200, _search_page(
                ids=("a", "b"),
                next_url="http://localhost/search/songs?query=jazz&country=br&limit=2&page=2",
            )
        return 200, _search_page(page=2, ids=("b", "c"))

    monkeypatch.setattr(bench, "wsgi_get", fake_transport)
    row = bench.run_one(
        "/search/songs",
        {"page": "1", "limit": "2", "query": "jazz", "country": "br"},
        country="br", profile="deep", seed=9,
    )

    assert len(calls) == 2
    assert calls[1][1]["page"] == "2"
    assert row["result"] == "fail"
    assert "duplicate" in row["reason"]
    assert row["followup"]["result"] == "fail"


def test_deep_runner_records_absent_next_page_instead_of_claiming_it_tested(monkeypatch):
    calls = []
    monkeypatch.setattr(
        bench, "wsgi_get",
        lambda path, params: (calls.append(path) or 200, _search_page(ids=("a",))),
    )
    row = bench.run_one(
        "/search/songs", {"page": "1", "limit": "2", "query": "jazz"},
        country="us", profile="deep", seed=11,
    )
    assert row["result"] == "pass"
    assert len(calls) == 1
    assert row["followup"]["result"] == "not_applicable"
