"""Curator discovery/quality diagnostics: offline, no Apple network."""
from scripts import catalog_curator_probe as probe


def test_curator_with_editorial_sections_but_no_playlists_is_not_marked_absent():
    detail = {
        "id": "321", "name": "Radio stories", "curator_type": "apple",
        "playlists": [], "sections": [
            {"id": "room1", "items": [{"id": "show1", "type": "stations"}]}
        ]
    }
    paging = {"curator_id": "321", "playlists": [], "current_page": 1}
    row = probe.classify_curator("321", 200, detail, 200, paging)
    assert row["status"] == "editorial_only"
    assert row["detail_playlist_count"] == 0
    assert row["editorial_item_count"] == 1
    assert row["paged_playlist_count"] == 0


def test_curator_with_actual_paged_playlists_is_verified():
    details = {"id": "11", "name": "Curated", "curator_type": "external",
               "playlists": [], "sections": []}
    paging = {"curator_id": "11", "playlists": [{"id": "pl.1"}]}
    assert probe.classify_curator("11", 200, details, 200, paging)["status"] == "with_playlists"


def test_cross_identity_curator_cannot_be_declared_valid():
    details = {"id": "999", "name": "Different", "playlists": [{"id": "pl.1"}]}
    paging = {"curator_id": "321", "playlists": [{"id": "pl.1"}]}
    assert probe.classify_curator("321", 200, details, 200, paging)["status"] == "invalid"


def test_curator_with_no_content_remains_empty_even_if_http_200():
    details = {"id": "321", "name": "Empty", "playlists": [], "sections": []}
    paging = {"curator_id": "321", "playlists": []}
    assert probe.classify_curator("321", 200, details, 200, paging)["status"] == "empty"


def test_choose_candidate_prefers_playlist_evidence_without_hiding_empty_trials():
    candidates = [
        {"id": "1", "source": "artist-query", "status": "empty"},
        {"id": "2", "source": "curator-search", "status": "with_playlists"},
        {"id": "3", "source": "curator-search", "status": "editorial_only"},
    ]
    choice = probe.select_verified(candidates, seed=3)
    assert choice["id"] == "2"
    assert len(candidates) == 3
    assert candidates[0]["status"] == "empty"


def test_no_verified_candidate_is_not_reported_as_a_success():
    assert probe.select_verified([{"id": "1", "status": "empty"}], seed=0) is None
