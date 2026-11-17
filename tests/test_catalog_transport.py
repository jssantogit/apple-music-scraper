"""Offline regressions for catalog transport and relationship pagination.

No calls to music.apple.com: all external reads are replaced with deterministic fakes.
"""
import json

import pytest

from apple_music import fetch


class FakeResponse:
    status_code = 200

    def __init__(self, body):
        self.text = body

    def json(self):
        return json.loads(self.text)


class FakeSession:
    def __init__(self, body):
        self.body = body
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse(self.body)


def test_malformed_json_with_object_prefix_retries_then_reports_upstream_failure(monkeypatch):
    session = FakeSession('{"data":')
    monkeypatch.setattr(fetch, "_session", lambda: session)
    monkeypatch.setattr(fetch, "_drop_session", lambda: None)
    monkeypatch.setattr(fetch, "developer_token", lambda force=False: "test-token")
    monkeypatch.setattr(fetch.config, "MAX_RETRIES", 2)
    monkeypatch.setattr(fetch.config, "RETRY_BACKOFF", 0)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    with pytest.raises(fetch.AppleMusicBlocked, match="non-JSON"):
        fetch.api_get("/v1/catalog/us/songs/123")

    assert session.calls == 2


def test_follow_all_stops_when_upstream_next_page_is_empty(monkeypatch):
    next_url = "/v1/catalog/us/albums/123/tracks?offset=1"
    requests = []

    def fake_api_get(path, params, *, lang=None):
        requests.append((path, params))
        if len(requests) > 1:
            pytest.fail("re-requested an empty upstream page")
        return {"data": [], "next": next_url}

    monkeypatch.setattr(fetch, "api_get", fake_api_get)
    result = fetch.follow_all(
        {"data": [{"id": "first"}], "next": next_url},
        max_items=20,
    )

    assert [item["id"] for item in result] == ["first"]
    assert len(requests) == 1


def test_follow_all_does_not_revisit_a_cyclic_next_link(monkeypatch):
    next_url = "/v1/catalog/us/albums/123/tracks?offset=1"
    requests = []

    def fake_api_get(path, params, *, lang=None):
        requests.append((path, params))
        if len(requests) > 1:
            pytest.fail("revisited a next link already fetched")
        return {"data": [{"id": "second"}], "next": next_url}

    monkeypatch.setattr(fetch, "api_get", fake_api_get)
    result = fetch.follow_all(
        {"data": [{"id": "first"}], "next": next_url},
        max_items=20,
    )

    assert [item["id"] for item in result] == ["first", "second"]
    assert len(requests) == 1


def test_follow_all_requests_only_the_remaining_item_budget(monkeypatch):
    next_url = "/v1/catalog/us/albums/123/tracks?offset=2"
    limits = []

    def fake_api_get(path, params, *, lang=None):
        limits.append(int(params["limit"]))
        return {"data": [{"id": "last"}], "next": None}

    monkeypatch.setattr(fetch, "api_get", fake_api_get)
    result = fetch.follow_all(
        {"data": [{"id": "a"}, {"id": "b"}], "next": next_url},
        max_items=3,
        max_per_call=100,
    )

    assert len(result) == 3
    assert limits == [1]
