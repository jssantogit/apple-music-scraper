"""Offline specification for the 51-endpoint rotating CI workbench.

These tests never send requests to Apple.
"""
from pathlib import Path

import pytest

import routes
from schema_fields import load_query
from scripts import catalog_bench as bench


@pytest.fixture
def context():
    return {
        "song": "617154366",
        "songs": ["617154366", "697195462"],
        "album": "1440871397",
        "artist": "5468295",
        "playlist": "pl.f4d106fed2bd41149aaacabb233eb5eb",
        "video": "1896761455",
        "station": "ra.978194965",
        "curator": "1526756058",
        "label": "1556733255",
        "genre": "21",
        "section": "12345678",
        "city": "New York City",
        "region": "global",
    }


def test_manifest_covers_every_route_and_catches_new_endpoints():
    actual = {route[0] for route in routes.ENDPOINTS}
    assert len(actual) == 51
    assert set(bench.REQUIRED_RESPONSE_KEYS) == actual


def test_rotating_case_pool_is_reproducible_but_not_fixed():
    pool = bench.read_case_pool()
    assert len(pool["portfolios"]) >= 5
    first = bench.choose_portfolio(pool, seed=0)
    assert first == bench.choose_portfolio(pool, seed=0)
    assert first != bench.choose_portfolio(pool, seed=1)
    assert bench.choose_portfolio(pool, seed=len(pool["portfolios"])) == first


@pytest.mark.parametrize("seed", [0, 1, 6, 199])
def test_all_51_routes_have_schema_valid_positive_cases(context, seed):
    for path, schema, _handler, _paginated in routes.ENDPOINTS:
        params = bench.case_for(path, context, country="br", term="Daft Punk", seed=seed)
        decoded, error = load_query(schema, params)
        assert error is None, f"{path}: {error}"
        assert decoded is not None


def test_missing_dynamic_fixture_is_a_failure_and_never_a_green_skip(context):
    del context["section"]
    with pytest.raises(bench.FixtureMissing, match="section"):
        bench.case_for("/browse/section", context, country="br", term="Daft Punk", seed=0)


def test_validation_rejects_200_with_wrong_shape_or_empty_identity():
    failed = bench.validate_result("/artists/details", 200, {"id": None, "name": "Example"}, {})
    assert failed["result"] == "fail"
    assert "top_songs" in failed["reason"] or "identity" in failed["reason"]


def test_empty_editorial_shelf_is_warning_not_false_positive():
    payload = {"section": {"id": None, "title": "Coming Soon"}, "items": [],
               "current_page": 1, "per_page": 5, "note": "not active"}
    checked = bench.validate_result("/browse/coming-soon", 200, payload, {"page": "1"})
    assert checked["result"] == "warn"


@pytest.mark.parametrize("prefix", ["", "/apple-music"])
def test_unknown_parameters_are_rejected_for_every_http_alias_without_network(prefix):
    for path, _schema, _handler, _paginated in routes.ENDPOINTS:
        status, response = bench.wsgi_get(prefix + path, {"__unexpected__": "1"})
        assert status == 400, path
        assert "error" in response


def test_report_fails_closed_on_unexecuted_endpoints():
    report = bench.summarize([
        {"path": "/songs/details", "result": "pass", "elapsed_ms": 4},
    ], expected_routes={"/songs/details", "/artists/details"})
    assert report["uncovered"] == ["/artists/details"]
    assert report["passed"] is False


def test_sanitize_error_never_emits_jwt():
    redacted = bench.safe_error("bad eyJhbGciOiJFUzI1NiJ9.eyJpc3MiOiJBTlQifQ.abc123 secret")
    assert "eyJ" not in redacted
