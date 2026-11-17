"""Small, read-only diagnostic for the underlying Apple search offset.

Run explicitly after a duplicate search-result ID is detected by the bench.
Prints only public IDs, never raw catalog resources or authentication headers.
"""
import argparse
import json
import time

from apple_music.fetch import catalog_get
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
    return data


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
            left = _raw_search(args.country, args.term, limit, 0)
            time.sleep(0.4)
            right = _raw_search(args.country, args.term, limit, limit)
            sample = inspect_pair(left, right)
            sample.update({"limit": limit, "round": round_no + 1})
            report["checks"].append(sample)
            time.sleep(0.4)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
