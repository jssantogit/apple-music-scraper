"""Read-only regional Browse shelf diagnostic; prints IDs and titles, not payloads.

The listing intentionally includes empty prefetched shelves. It distinguishes
absent Apple editorial rooms from rooms dropped by the local parser / index.
"""
import argparse
import json

from apple_music import refs
from apple_music.shared import grouping


def _data(parent, key):
    obj = (parent or {}).get("relationships") or {}
    rel = obj.get(key) or {}
    return rel.get("data") or []


def inspect_grouping(body):
    roots = (body or {}).get("data") or []
    if not roots:
        return {"linked_rooms": 0, "visible_with_items": 0, "rooms": [], "tabs": 0}
    tabs = _data(roots[0], "tabs")
    rooms = []
    for tab_number, tab in enumerate(tabs):
        for shelf in _data(tab, "children"):
            room_links = _data(shelf, "room")
            room_id = next((r.get("id") for r in room_links if isinstance(r, dict)
                            and r.get("id")), None)
            if not room_id:
                continue
            a = shelf.get("attributes") or {}
            content = _data(shelf, "contents")
            for child in _data(shelf, "children"):
                content += _data(child, "contents")
            rooms.append({
                "title": a.get("name") or a.get("title"),
                "room_id": str(room_id),
                "items": len(content),
                "tab": tab_number,
            })
    return {
        "linked_rooms": len(rooms),
        "visible_with_items": sum(r["items"] > 0 for r in rooms),
        "rooms": rooms,
        "tabs": len(tabs),
    }


def evaluate_shortcuts(rooms):
    results = {}
    for key, title in refs.BROWSE_SECTIONS.items():
        exact = next((room for room in rooms if room["title"] == title), None)
        keyword = refs.BROWSE_SECTION_KEYWORDS.get(key, title.lower())
        fallback = next((room for room in rooms
                         if keyword in (room["title"] or "").lower()), None)
        choice, method = ((exact, "exact_title") if exact else
                          (fallback, "keyword") if fallback else
                          (None, "unresolved"))
        results[key] = {"room_id": choice["room_id"] if choice else None,
                        "source": method}
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countries", nargs="+", choices=("br", "fr", "us", "jp", "in"),
                        default=("br", "fr", "us"))
    args = parser.parse_args(argv)
    report = {}
    for country in args.countries:
        result = inspect_grouping(grouping(country, lang="en-US", name="music"))
        report[country.upper()] = {
            "tabs": result["tabs"],
            "linked_rooms": result["linked_rooms"],
            "visible_with_items": result["visible_with_items"],
            "rooms": result["rooms"][:80],
            "shortcuts": evaluate_shortcuts(result["rooms"]),
        }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
