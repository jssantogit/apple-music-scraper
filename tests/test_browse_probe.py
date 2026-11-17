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
