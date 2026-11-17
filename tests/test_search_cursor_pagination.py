"""Search pagination must use Apple's actual next cursor, not arithmetic offsets."""

import pytest

from apple_music import search
from apple_music.fetch import AppleMusicUpstreamError


def _item(value):
    return {"id": value, "type": "songs", "attributes": {"name": value}}


def test_page_two_uses_apple_next_cursor_offset_instead_of_limit(monkeypatch):
    calls = []
    next_url = "/v1/catalog/in/search?term=Yo-Yo+Ma&types=songs&offset=9"

    def first(sf, path, params, *, lang=None):
        calls.append(("first", sf, path, dict(params)))
        return {"results": {"songs": {
            "data": [_item("first"), _item("second")], "next": next_url,
        }}}

    def second(path, params, *, lang=None):
        calls.append(("next", path, dict(params)))
        assert path == "/v1/catalog/in/search"
        assert params["offset"] == "9"
        assert int(params["limit"]) == 2
        return {"results": {"songs": {
            "data": [_item("third"), _item("fourth")], "next": None,
        }}}

    monkeypatch.setattr(search, "catalog_get", first)
    monkeypatch.setattr(search, "api_get", second)
    result = search.search_songs("Yo-Yo Ma", page=2, limit=2, country="in")
    assert [row["id"] for row in result["songs"]] == ["third", "fourth"]
    assert result["pagination"]["page"] == 2
    assert len(calls) == 2


def test_page_three_follows_next_chained_from_second_page(monkeypatch):
    calls = []
    urls = iter((
        "/v1/catalog/in/search?term=Jazz&types=songs&offset=9",
        "/v1/catalog/in/search?term=Jazz&types=songs&offset=17",
    ))
    monkeypatch.setattr(
        search, "catalog_get",
        lambda *args, **kwargs: {"results": {"songs": {
            "data": [_item("a")], "next": next(urls),
        }}},
    )

    def next_request(path, params, *, lang=None):
        calls.append(params["offset"])
        return {"results": {"songs": {
            "data": [_item("b" if len(calls) == 1 else "c")],
            "next": "/v1/catalog/in/search?term=Jazz&types=songs&offset=17"
            if len(calls) == 1 else None,
        }}}

    monkeypatch.setattr(search, "api_get", next_request)
    data = search.search_songs("Jazz", page=3, limit=1, country="in")
    assert [row["id"] for row in data["songs"]] == ["c"]
    assert calls == ["9", "17"]


def test_missing_next_cursor_returns_empty_page_without_reattempt(monkeypatch):
    calls = []
    monkeypatch.setattr(
        search, "catalog_get",
        lambda *args, **kwargs: {"results": {"songs": {"data": [_item("only")]}}},
    )
    monkeypatch.setattr(
        search, "api_get", lambda *args, **kwargs: calls.append(1),
    )
    page = search.search_songs("only", page=2, limit=2, country="us")
    assert page["songs"] == []
    assert not calls


@pytest.mark.parametrize("bad_url", [
    "https://evil.example/v1/catalog/in/search?offset=9",
    "/v1/catalog/us/search?offset=9",
])
def test_external_or_other_storefront_cursor_fails_closed(monkeypatch, bad_url):
    monkeypatch.setattr(
        search, "catalog_get",
        lambda *args, **kwargs: {"results": {"songs": {
            "data": [_item("first")], "next": bad_url,
        }}},
    )
    with pytest.raises(AppleMusicUpstreamError, match="cursor"):
        search.search_songs("Jazz", page=2, limit=1, country="in")


def test_cyclic_search_next_cursor_rejected(monkeypatch):
    cursor = "/v1/catalog/in/search?types=songs&offset=9"
    monkeypatch.setattr(search, "catalog_get", lambda *args, **kwargs: {
        "results": {"songs": {"data": [_item("a")], "next": cursor}}
    })
    monkeypatch.setattr(search, "api_get", lambda *args, **kwargs: {
        "results": {"songs": {"data": [_item("b")], "next": cursor}}
    })
    with pytest.raises(AppleMusicUpstreamError, match="cursor"):
        search.search_songs("Jazz", page=3, limit=1, country="in")


def _curator(identifier, kind):
    return {"id": identifier, "type": kind, "attributes": {"name": identifier}}


def test_combined_curators_pagination_never_exceeds_shared_limit(monkeypatch):
    seen = []

    def fetch(sf, path, params, *, lang=None):
        seen.append(params["types"])
        if params["types"] == "apple-curators":
            return {"results": {"apple-curators": {
                "data": [_curator("apple1", "apple-curators")], "next": None,
            }}}
        if params["types"] == "curators":
            return {"results": {"curators": {
                "data": [_curator("third1", "curators"), _curator("third2", "curators")],
                "next": None,
            }}}
        raise AssertionError("combined Apple and external curator results must be fetched separately")

    monkeypatch.setattr(search, "catalog_get", fetch)
    monkeypatch.setattr(search, "api_get", lambda *args, **kwargs: pytest.fail("unexpected cursor"))
    first = search.search_curators("curated", page=1, limit=2, country="us")
    second = search.search_curators("curated", page=2, limit=2, country="us")
    assert [item["id"] for item in first["curators"]] == ["apple1", "third1"]
    assert [item["id"] for item in second["curators"]] == ["third2"]
    assert first["pagination"]["total_pages"] == 2
    assert second["pagination"]["total_pages"] == 2
    assert "apple-curators" in seen and "curators" in seen


def test_combined_curators_follows_first_resource_type_cursor_before_next_type(monkeypatch):
    calls = []

    def first(sf, path, params, *, lang=None):
        calls.append(("first", params["types"]))
        if params["types"] == "apple-curators":
            return {"results": {"apple-curators": {
                "data": [_curator("apple1", "apple-curators"),
                         _curator("apple2", "apple-curators")],
                "next": "/v1/catalog/us/search?types=apple-curators&offset=9",
            }}}
        assert params["types"] == "curators"
        return {"results": {"curators": {"data": [], "next": None}}}

    def next_request(path, params, *, lang=None):
        calls.append(("next", params["offset"]))
        assert params["offset"] == "9"
        assert int(params["limit"]) == 2
        return {"results": {"apple-curators": {
            "data": [_curator("apple3", "apple-curators"),
                     _curator("apple4", "apple-curators")],
            "next": None,
        }}}

    monkeypatch.setattr(search, "catalog_get", first)
    monkeypatch.setattr(search, "api_get", next_request)
    page = search.search_curators("curated", page=2, limit=2, country="us")
    assert [item["id"] for item in page["curators"]] == ["apple3", "apple4"]
    # A final lookahead is permitted only after exhausting the first stream.
    assert calls == [("first", "apple-curators"), ("next", "9"),
                     ("first", "curators")]


def test_combined_curators_looks_ahead_at_exact_resource_boundary(monkeypatch):
    types_seen = []

    def first(sf, path, params, *, lang=None):
        kind = params["types"]
        types_seen.append(kind)
        if kind == "apple-curators":
            return {"results": {kind: {"data": [
                _curator("apple1", kind), _curator("apple2", kind),
            ], "next": None}}}
        return {"results": {kind: {"data": [
            _curator("third1", kind),
        ], "next": None}}}

    monkeypatch.setattr(search, "catalog_get", first)
    first_page = search.search_curators("mix", page=1, limit=2, country="us")
    second_page = search.search_curators("mix", page=2, limit=2, country="us")
    assert [item["id"] for item in first_page["curators"]] == ["apple1", "apple2"]
    assert first_page["pagination"]["total_pages"] == 2
    assert [item["id"] for item in second_page["curators"]] == ["third1"]
    assert types_seen.count("curators") >= 1
