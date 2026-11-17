"""Read-only regional Browse shelf diagnostic; prints IDs and titles, not payloads.

The listing intentionally includes empty prefetched shelves. It distinguishes
absent Apple editorial rooms from rooms dropped by the local parser / index.
"""
import argparse
import json

from apple_music import browse, refs
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


def evaluate_shortcuts(rooms, country="us"):
    """Report matches using the production resolver, not a second heuristic."""
    index = {r["title"]: r["room_id"] for r in rooms if r.get("title")}
    results = {}
    for key, english in refs.BROWSE_SECTIONS.items():
        identifier = browse.resolve_browse_room_id(index, key, country)
        aliases = refs.BROWSE_LOCALIZED_TITLES.get(country, {})
        matched_title = next(
            (r["title"] for r in rooms if r["room_id"] == identifier), None
        )
        if identifier is None:
            source = "unresolved"
        elif matched_title == english:
            source = "exact_title"
        elif matched_title == aliases.get(key):
            source = "localized_title"
        else:
            source = "keyword"
        results[key] = {"room_id": identifier, "source": source}
    return results


def verify_routes(country, rooms, request):
    """Compare each live shortcut result with a real room in the same grouping."""
    indexes = evaluate_shortcuts(rooms, country)
    by_id = {r["room_id"]: r for r in rooms}
    checks = []
    for key, resolved in indexes.items():
        endpoint = "/browse/" + key
        room_id = resolved["room_id"]
        result = {"endpoint": endpoint, "room_id": room_id}
        try:
            code, body = request(endpoint, {
                "country": country, "lang": "en-US", "page": "1", "limit": "3"
            })
        except Exception as exc:
            result.update(result="fail", reason="request raised " + type(exc).__name__)
            checks.append(result)
            continue
        if not isinstance(body, dict) or code != 200:
            result.update(result="fail", reason="HTTP " + str(code))
        else:
            returned_room = (body.get("section") or {}).get("id")
            items = body.get("items")
            if not isinstance(items, list):
                result.update(result="fail", reason="items is not an array")
            elif room_id is None:
                if returned_room is None and not items and body.get("note"):
                    result.update(result="unavailable", reason="not listed by Apple")
                else:
                    result.update(result="fail", reason="unlisted shortcut returned a room")
            elif str(returned_room) != str(room_id):
                result.update(result="fail", reason="resolved room ID mismatch")
            elif any(not isinstance(item, dict) for item in items):
                result.update(result="fail", reason="items contains a non-object")
            elif not items and by_id[room_id]["items"] > 0:
                result.update(result="fail", reason="empty room despite preview items")
            elif not items:
                result.update(result="warn", reason="room returned no contents")
            else:
                result.update(result="pass", observed_items=len(items), reason="")
        checks.append(result)
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countries", nargs="+", choices=("br", "fr", "us", "jp", "in"),
                        default=("br", "fr", "us"))
    parser.add_argument("--verify-shortcuts", action="store_true",
                        help="Also call each real Bottle shortcut and validate room IDs/content")
    args = parser.parse_args(argv)
    report = {}
    failed = False
    if args.verify_shortcuts:
        from scripts.catalog_bench import wsgi_get
    for country in args.countries:
        result = inspect_grouping(grouping(country, lang="en-US", name="music"))
        entry = {
            "tabs": result["tabs"],
            "linked_rooms": result["linked_rooms"],
            "visible_with_items": result["visible_with_items"],
            "rooms": result["rooms"][:80],
            "shortcuts": evaluate_shortcuts(result["rooms"], country),
        }
        if args.verify_shortcuts:
            entry["checks"] = verify_routes(country, result["rooms"], wsgi_get)
            failed = failed or any(row["result"] == "fail" for row in entry["checks"])
        report[country.upper()] = entry
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
