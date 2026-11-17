"""Contract for diagnosing regional Browse rooms without leaking catalog payloads."""
from scripts import catalog_browse_probe as probe


def grouping_fixture():
    return {
        "data": [{
            "relationships": {"tabs": {"data": [{
                "relationships": {"children": {"data": [
                    {"id": "hero", "attributes": {"name": "Just Added"},
                     "relationships": {
                         "room": {"data": [{"id": "2201"}]},
                         "contents": {"data": [{"id": "a", "type": "songs",
                                                "attributes": {"name": "Example"}}]},
                     }},
                    {"id": "empty", "attributes": {"name": "New This Week"},
                     "relationships": {"room": {"data": [{"id": "2202"}]},
                                       "contents": {"data": []}}},
                    {"id": "custom", "attributes": {"name": "Mais ouvidas"},
                     "relationships": {"room": {"data": [{"id": "2203"}]},
                                       "contents": {"data": []}}},
                ]}}
            }]}}
        }]
    }


def test_probe_keeps_linked_rooms_even_when_prefetched_items_are_empty():
    result = probe.inspect_grouping(grouping_fixture())
    assert [(r["title"], r["room_id"], r["items"]) for r in result["rooms"]] == [
        ("Just Added", "2201", 1), ("New This Week", "2202", 0),
        ("Mais ouvidas", "2203", 0)]
    assert result["visible_with_items"] == 1
    assert result["linked_rooms"] == 3


def test_probe_marks_shortcut_resolution_without_inventing_new_room():
    rooms = probe.inspect_grouping(grouping_fixture())["rooms"]
    resolved = probe.evaluate_shortcuts(rooms)
    assert resolved["new-releases"]["room_id"] == "2202"
    assert resolved["new-releases"]["source"] == "exact_title"
    assert resolved["best-new-songs"]["room_id"] is None
    assert resolved["best-new-songs"]["source"] == "unresolved"



def test_probe_uses_production_localized_resolver():
    rooms = [
        {"title": "Novidades da semana", "room_id": "br210", "items": 20},
        {"title": "Em breve", "room_id": "br211", "items": 20},
    ]
    matches = probe.evaluate_shortcuts(rooms, country="br")
    assert matches["new-releases"] == {"room_id": "br210", "source": "localized_title"}
    assert matches["coming-soon"] == {"room_id": "br211", "source": "localized_title"}
    assert matches["recent-releases"]["source"] == "unresolved"


def test_live_verifier_rejects_empty_shortcut_when_apple_shows_room_items():
    rooms = [{"title": "Novidades da semana", "room_id": "br210", "items": 20}]
    def transport(path, args):
        return 200, {
            "section": {"id": "br210", "title": "Novidades da semana"},
            "items": [], "current_page": 1, "per_page": 3,
            "total_pages": 1, "next": None, "previous": None,
        }
    result = probe.verify_routes("br", rooms, transport)
    selected = next(x for x in result if x["endpoint"] == "/browse/new-releases")
    assert selected["result"] == "fail"
    assert "empty" in selected["reason"]


def test_live_verifier_reports_genuinely_unlisted_room_as_unavailable():
    rooms = [{"title": "Best New Songs", "room_id": "jp111", "items": 10}]
    def transport(path, args):
        if path == "/browse/best-new-songs":
            return 200, {
                "section": {"id": "jp111", "title": "Best New Songs"},
                "items": [{"id": "1"}], "current_page": 1, "per_page": 3,
                "total_pages": 2, "next": None, "previous": None,
            }
        return 200, {
            "section": {"id": None, "title": "Not advertised"},
            "items": [], "note": "not in storefront",
            "current_page": 1, "per_page": 3, "total_pages": 1,
            "next": None, "previous": None,
        }
    results = probe.verify_routes("jp", rooms, transport)
    selected = next(x for x in results if x["endpoint"] == "/browse/dj-mixes")
    assert selected["result"] == "unavailable"
    assert not any(x["result"] == "fail" for x in results)
