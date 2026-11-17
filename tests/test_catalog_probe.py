"""Pure validators for the optional, bounded BR/US catalog probe."""

import pytest

from scripts.catalog_live_probe import choose_entity, summarize_country


def test_choose_entity_requires_an_id_and_name():
    rows = [
        None,
        {"id": "1", "name": ""},
        {"id": "", "name": "X"},
        {"id": "42", "name": "Artist", "artwork": None},
    ]
    assert choose_entity(rows)["id"] == "42"


def test_summarize_country_never_confuses_metadata_presence_with_full_audio_access():
    artist = {"id": "artist-1", "top_songs": [{"id": "song-1"}],
              "albums": [{"id": "album-1"}], "singles_and_eps": [],
              "similar_artists": [], "artwork": {"link": "https://example.com/art.jpg"}}
    album = {"id": "album-1", "tracks": [{"id": "song-1"}],
             "artwork": {"link": "https://example.com/album.jpg"}}
    song = {"id": "song-1", "isrc": "USAAA0000001",
            "audio_traits": ["lossless"], "preview_link": None}
    summary = summarize_country("br", artist, album, song)

    assert summary["country"] == "BR"
    assert summary["artist"]["top_songs_count"] == 1
    assert summary["artist"]["similar_artists_count"] == 0
    assert summary["album"]["track_count_observed"] == 1
    assert summary["song"]["has_isrc"] is True
    assert summary["song"]["has_full_stream"] is False


@pytest.mark.parametrize("country", ["br", "us"])
def test_probe_summary_preserves_country_in_result(country):
    result = summarize_country(country, {"id": "1"}, {"id": "2"}, {"id": "3"})
    assert result["country"] == country.upper()
