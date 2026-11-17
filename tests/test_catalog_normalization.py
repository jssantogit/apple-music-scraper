"""Offline regressions for Apple Music catalog normalization and partial shelves."""

import pytest

from apple_music import parsers, search


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-16T23:30:00-03:00", "2026-11-17T02:30:00Z"),
        ("2026-01-01T00:30:00+02:00", "2025-12-31T22:30:00Z"),
        ("2026-09-19T07:42:19Z", "2026-09-19T07:42:19Z"),
        ("2026-01-01T00:30:00", None),
    ],
)
def test_iso_datetime_only_labels_converted_utc_time_as_z(raw, expected):
    assert parsers.iso_datetime(raw) == expected


def test_playlist_timestamp_uses_utc_instead_of_local_wall_time():
    playlist = {
        "id": "pl.sample",
        "type": "playlists",
        "attributes": {
            "name": "Curated",
            "lastModifiedDate": "2026-11-16T23:30:00-03:00",
        },
    }
    assert parsers.playlist(playlist)["last_modified_at"] == "2026-11-17T02:30:00Z"


def test_search_all_tolerates_null_curator_data(monkeypatch):
    core = {
        "results": {
            "songs": {"data": [{"id": "song1", "type": "songs", "attributes": {"name": "A"}}]},
            "albums": {"data": []},
            "artists": {"data": []},
            "playlists": {"data": []},
        }
    }
    extra = {"results": {"apple-curators": {"data": None}, "curators": {"data": []}}}
    monkeypatch.setattr(search, "run_parallel", lambda fns: [core, extra])

    results = search.search_all("A", country="br")

    assert results["songs"][0]["id"] == "song1"
    assert results["curators"] == []
    assert results["query"] == "A"
