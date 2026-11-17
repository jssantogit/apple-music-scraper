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
