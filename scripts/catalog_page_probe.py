"""Small, read-only diagnostic for the underlying Apple search offset.

Run explicitly after a duplicate search-result ID is detected by the bench.
Prints only public IDs, never raw catalog resources or authentication headers.
"""
import argparse
import json
import time
from urllib.parse import parse_qsl, urlsplit

from apple_music.fetch import api_get, catalog_get
from apple_music import parsers as P


def inspect_pair(first, second):
    left = [str(obj["id"]) for obj in first if isinstance(obj, dict) and obj.get("id")]
    right = [str(obj["id"]) for obj in second if isinstance(obj, dict) and obj.get("id")]
    return {
        "page1_ids": left,
        "page2_ids": right,
        "overlap_ids": sorted(set(left) & set(right)),
        "page1_count": len(left),
        "page2_count": len(right),
    }


def parse_next_cursor(next_link, *, country):
    """Use only a relative or first-party Apple search cursor."""
    parsed = urlsplit(next_link or "")
    expected = f"/v1/catalog/{country.lower()}/search"
    if (parsed.path != expected or parsed.scheme not in ("", "https") or
            parsed.netloc not in ("", "amp-api.music.apple.com")):
        raise ValueError("invalid Apple search next cursor")
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if not params:
        raise ValueError("empty Apple search cursor")
    return expected, params


def _raw_search(country, term, limit, offset):
    body = catalog_get(country, "search", {
        "term": term, "types": "songs", "limit": limit, "offset": offset or None,
    }, lang="en-US")
    block = (((body or {}).get("results") or {}).get("songs") or {})
    data = block.get("data") or []
    if not isinstance(data, list):
        raise ValueError("upstream search results.songs.data is not an array")
    normalized = P.items(data)
    raw_ids = [str(x["id"]) for x in data if isinstance(x, dict) and x.get("id")]
    parsed_ids = [str(x["id"]) for x in normalized if x.get("id")]
    if raw_ids != parsed_ids:
        raise ValueError("scraper parser changed the song IDs in a search result")
    return data, block.get("next")


def _from_cursor(country, cursor):
    path, params = parse_next_cursor(cursor, country=country)
    body = api_get(path, params, lang="en-US")
    return ((((body or {}).get("results") or {}).get("songs") or {}).get("data") or [])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="in")
    parser.add_argument("--term", default="Yo-Yo Ma")
    parser.add_argument("--limits", default="2,5,10")
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args(argv)
    limits = [int(v) for v in args.limits.split(",")]
    if len(limits) > 3 or not limits or any(v < 1 or v > 25 for v in limits):
        parser.error("choose 1 to 3 page sizes between 1 and 25")
    if not 1 <= args.rounds <= 3:
        parser.error("--rounds must be between 1 and 3")
    report = {"country": args.country, "term": args.term, "checks": []}
    for limit in limits:
        for round_no in range(args.rounds):
            left, next_cursor = _raw_search(args.country, args.term, limit, 0)
            time.sleep(0.4)
            right, _ = _raw_search(args.country, args.term, limit, limit)
            sample = inspect_pair(left, right)
            sample.update({"limit": limit, "round": round_no + 1,
                           "has_upstream_next": bool(next_cursor)})
            if next_cursor:
                path, next_query = parse_next_cursor(next_cursor, country=args.country)
                time.sleep(0.4)
                cursor_page = _from_cursor(args.country, next_cursor)
                followed = inspect_pair(left, cursor_page)
                sample["cursor_path"] = path
                sample["cursor_offset_params"] = {
                    key: value for key, value in next_query.items()
                    if "offset" in key or key == "limit"
                }
                sample["cursor_page_ids"] = followed["page2_ids"]
                sample["cursor_overlap_ids"] = followed["overlap_ids"]
            report["checks"].append(sample)
            time.sleep(0.4)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
