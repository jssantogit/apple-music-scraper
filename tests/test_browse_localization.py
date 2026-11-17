"""Regression coverage for localized Apple editorial Browse shortcuts."""
import pytest

from apple_music import browse, refs, shared


BR = {
    "best-new-songs": "Melhores músicas novas",
    "new-releases": "Novidades da semana",
    "recent-releases": "Lançamentos recentes",
    "updated-playlists": "Playlists atualizadas",
    "trending-songs": "Músicas em alta",
    "popular": "Só se ouve…",
    "dj-mixes": "DJ mixes mais recentes",
    "coming-soon": "Em breve",
}
FR = {
    "best-new-songs": "Titres du moment",
    "new-releases": "Nouveautés de la semaine",
    "recent-releases": "Sorties récentes",
    "updated-playlists": "Playlists mises à jour",
    "trending-songs": "Titres tendances",
    "popular": "Tout le monde écoute...",
    "dj-mixes": "Derniers DJ mixes",
    "coming-soon": "Bientôt disponible",
}


@pytest.mark.parametrize("country,names", [("br", BR), ("fr", FR)])
def test_all_8_localized_shortcuts_resolve_distinct_room_ids(country, names):
    rooms = {name: str(9000 + i) for i, name in enumerate(names.values())}
    found = {name: browse.resolve_browse_room_id(rooms, name, country)
             for name in names}
    assert found == {name: rooms[title] for name, title in names.items()}
    assert len(set(found.values())) == 8


@pytest.mark.parametrize("name,title", list(refs.BROWSE_SECTIONS.items()))
def test_all_english_shortcuts_still_resolve(name, title):
    assert browse.resolve_browse_room_id({title: "777"}, name, "us") == "777"


def test_localized_match_is_robust_to_accent_and_ellipsis_normalization():
    assert browse.resolve_browse_room_id({"So se ouve...": "12"}, "popular", "br") == "12"
    assert browse.resolve_browse_room_id({"TOUT LE MONDE ÉCOUTE…": "22"}, "popular", "fr") == "22"


def test_unknown_locale_does_not_guess_by_position_or_other_titles():
    assert browse.resolve_browse_room_id(
        {"Best New Songs": "1", "Recent Releases": "2"},
        "updated-playlists", "xx"
    ) is None


def test_missing_japanese_dj_mixes_is_not_fabricated():
    rooms = {"Best New Songs": "101", "New This Week": "102"}
    assert browse.resolve_browse_room_id(rooms, "dj-mixes", "jp") is None


def test_room_index_keeps_linked_room_even_without_prefetched_items(monkeypatch):
    body = {"data": [{"relationships": {"tabs": {"data": [{
        "relationships": {"children": {"data": [
            {"attributes": {"name": "New This Week"},
             "relationships": {"room": {"data": [{"id": "2199"}]},
                               "contents": {"data": []}}},
            {"attributes": {"name": "Other section"},
             "relationships": {"room": {"data": [{"id": "2200"}]},
                               "contents": {"data": [{"id": "1", "type": "songs"}]}}},
            {"attributes": {"links": [{"label": "External", "url": "/link"}]}},
        ]}}
    }]}}}]}
    monkeypatch.setattr(shared, "grouping", lambda *args, **kwargs: body)
    monkeypatch.setattr(shared, "lookup", lambda key, build: build())
    assert shared.browse_room_ids("us") == {
        "New This Week": "2199", "Other section": "2200",
    }


@pytest.mark.parametrize("name,localized_title", list(BR.items()))
def test_shortcut_handler_uses_selected_brazilian_room(monkeypatch, name, localized_title):
    monkeypatch.setattr(browse, "browse_room_ids",
                        lambda country: {localized_title: "31001"})
    calls = []

    def details(room_id, **kwargs):
        calls.append((room_id, kwargs))
        return {"section": {"id": room_id}, "items": [{"id": "a"}]}

    monkeypatch.setattr(browse, "section", details)
    response = getattr(browse, name.replace("-", "_"))(country="br", limit=3)
    assert response["items"][0]["id"] == "a"
    assert calls[0][0] == "31001"
    assert calls[0][1]["country"] == "br"


def test_missing_localized_room_remains_explicit_empty_note(monkeypatch):
    monkeypatch.setattr(browse, "browse_room_ids",
                        lambda country: {"Some Other Shelf": "1"})
    result = browse.new_releases(country="br")
    assert result["section"]["id"] is None
    assert result["items"] == []
    assert result["note"]
