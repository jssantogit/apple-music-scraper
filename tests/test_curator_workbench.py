"""Curator fixture selection and semantic contract regressions (offline)."""
from scripts import catalog_bench as bench


def _detail(cid, *, playlists=(), sections=()):
    return {"id": cid, "name": "Public curator", "curator_type": "apple",
            "playlists": [{"id": x} for x in playlists],
            "sections": [{"items": [{"id": x} for x in sections]}] if sections else []}


def _page(cid, *playlist_ids):
    return {"curator_id": cid, "playlists": [{"id": x} for x in playlist_ids],
            "current_page": 1, "per_page": 4, "total_pages": 1,
            "next": None, "previous": None}


def test_editorial_only_curator_detail_is_contentful_not_empty():
    row = _detail("101", sections=["show1", "show2"])
    check = bench.validate_result("/curators/details", 200, row, {"curator": "101"})
    assert check["result"] == "pass"
    assert check["observed_count"] == 2


def test_curator_detail_with_empty_playlists_and_empty_sections_stays_warning():
    row = _detail("101")
    check = bench.validate_result("/curators/details", 200, row, {"curator": "101"})
    assert check["result"] == "warn"
    assert check["observed_count"] == 0


def test_curator_detail_with_broken_editorial_structure_is_failure():
    row = _detail("101")
    row["sections"] = [None]
    check = bench.validate_result("/curators/details", 200, row, {"curator": "101"})
    assert check["result"] == "fail"


def test_curator_discovery_prefers_verified_playlist_source_and_records_other_cases():
    calls = []

    def fetch(path, params):
        calls.append((path, dict(params)))
        if path == "/search/curators":
            return {"curators": [{"id": "202"}]}
        if path == "/curators/details":
            cid = params["curator"]
            return _detail(cid, sections=["radio"] if cid == "101" else [],
                           playlists=["pl.foo"] if cid == "202" else [])
        if path == "/curators/playlists":
            cid = params["curator"]
            return _page(cid, *([] if cid == "101" else ["pl.foo"]))
        raise AssertionError(path)

    candidate, evidence, trials = bench.resolve_curator_fixture(
        country="br", term="Artist", seed=0,
        pool={"search_cases": {"curators": ["Apple Music", "Beats 1"]},
              "fallback_ids": {}},
        get=fetch, initial=[{"id": "101"}],
    )
    assert candidate == "202"
    assert evidence["status"] == "with_playlists"
    assert {trial["status"] for trial in trials} == {"editorial_only", "with_playlists"}
    assert any("/curators/playlists" == path for path, _ in calls)


def test_discovery_keeps_editorial_only_case_when_no_playlist_curators_exist():
    def fetch(path, params):
        if path == "/search/curators":
            return {"curators": []}
        if path == "/curators/details":
            return _detail("101", sections=["radio"])
        if path == "/curators/playlists":
            return _page("101")
        raise AssertionError(path)

    cid, evidence, trials = bench.resolve_curator_fixture(
        country="fr", term="Jazz", seed=2,
        pool={"search_cases": {"curators": ["Apple Music"]}, "fallback_ids": {}},
        get=fetch, initial=[{"id": "101"}],
    )
    assert cid == "101"
    assert evidence["status"] == "editorial_only"
    assert len(trials) == 1


def test_discovery_does_not_claim_verified_without_a_valid_curator():
    def fetch(path, params):
        return {"curators": []} if path == "/search/curators" else {}

    cid, evidence, trials = bench.resolve_curator_fixture(
        country="br", term="Unknown", seed=1,
        pool={"search_cases": {"curators": ["Apple Music"]},
              "fallback_ids": {"curator": ["fail_id"]}},
        get=fetch, initial=[],
    )
    assert cid is None
    assert evidence is None
    assert len(trials) == 1
    assert trials[0]["status"] == "invalid"
