"""Small live curator fixture diagnostic; IDs and counts only, no raw payloads.

Compares curator details and paged playlists for dynamically discovered entities.
An editorial curator with shows but no playlists must not be called "empty".
"""
import argparse
from datetime import datetime, timezone
import json
import os
import time

from scripts.catalog_bench import read_case_pool, choose_portfolio, wsgi_get


def classify_curator(curator_id, detail_http, detail, playlist_http, paging):
    result = {"id": str(curator_id),
              "detail_http": detail_http, "playlist_http": playlist_http,
              "detail_playlist_count": 0, "paged_playlist_count": 0,
              "editorial_item_count": 0, "curator_type": None,
              "status": "invalid"}
    if (detail_http != 200 or playlist_http != 200
            or not isinstance(detail, dict) or not isinstance(paging, dict)):
        return result
    if str(detail.get("id")) != str(curator_id) or str(paging.get("curator_id")) != str(curator_id):
        return result
    playlists = detail.get("playlists")
    paged = paging.get("playlists")
    sections = detail.get("sections")
    if not isinstance(playlists, list) or not isinstance(paged, list) or not isinstance(sections, list):
        return result
    if any(not isinstance(item, dict) for item in playlists + paged + sections):
        return result
    section_items = sum(
        len(s.get("items") or []) for s in sections
        if isinstance(s.get("items") or [], list)
    )
    result.update(detail_playlist_count=len(playlists), paged_playlist_count=len(paged),
                  editorial_item_count=section_items,
                  curator_type=detail.get("curator_type"))
    if playlists or paged:
        result["status"] = "with_playlists"
    elif section_items > 0:
        result["status"] = "editorial_only"
    else:
        result["status"] = "empty"
    return result


def select_verified(candidates, seed=0):
    matches = [row for row in candidates if row.get("status") == "with_playlists"]
    if not matches:
        return None
    return matches[int(seed) % len(matches)]


def _safe_ids(payload, field):
    data = payload.get(field) or [] if isinstance(payload, dict) else []
    return [str(item["id"]) for item in data
            if isinstance(item, dict) and item.get("id")]


def run_country(country, term, seed, pool, max_candidates=6):
    base = {"country": country, "lang": "en-US"}
    sources = {}
    queries = [("search/all", term)]
    specialized = pool.get("search_cases", {}).get("curators") or []
    if specialized:
        queries.append(("search/curators", specialized[seed % len(specialized)]))
        queries.append(("search/curators", specialized[(seed + 1) % len(specialized)]))
    for route, query in queries:
        path = "/" + route
        params = {**base, "query": query, "limit": "6"}
        if route == "search/curators":
            params.update(page="1")
        status, payload = wsgi_get(path, params)
        if status != 200 or not isinstance(payload, dict):
            continue
        for cid in _safe_ids(payload, "curators"):
            sources.setdefault(cid, []).append(route + ":" + query)
    fallback = pool.get("fallback_ids", {}).get("curator") or []
    if not sources:
        for cid in fallback[:1]:
            sources.setdefault(str(cid), []).append("fallback")
    candidates = list(sources)
    # Rotate and bound the number of probed curators without fixed IDs.
    if candidates:
        pivot = seed % len(candidates)
        candidates = (candidates[pivot:] + candidates[:pivot])[:max_candidates]
    observed = []
    for cid in candidates:
        detail_http, detail = wsgi_get("/curators/details", {**base, "curator": cid})
        paging_http, paging = wsgi_get("/curators/playlists", {
            **base, "curator": cid, "page": "1", "limit": "4"
        })
        row = classify_curator(cid, detail_http, detail, paging_http, paging)
        row["source"] = sources[cid]
        observed.append(row)
        time.sleep(0.2)
    selected = select_verified(observed, seed)
    return {"storefront": country.upper(), "query": term,
            "found_candidates": len(sources), "tested_candidates": len(observed),
            "selected_curator": selected["id"] if selected else None,
            "selected_source": selected["source"] if selected else None,
            "candidates": observed,
            "status": "verified" if selected else "no_verified_playlist_fixture"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countries", nargs="+", default=("br", "fr"),
                        choices=("br", "fr", "us", "jp", "in", "gb"))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--term", default="")
    args = parser.parse_args(argv)
    seed = args.seed if args.seed is not None else int(os.getenv("GITHUB_RUN_NUMBER", "0"))
    pool = read_case_pool()
    term = args.term or choose_portfolio(pool, seed)["query"]
    report = {"seed": seed, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "countries": [run_country(country, term, seed, pool)
                            for country in args.countries]}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # This is a diagnostic, not the workbench gate. Missing fixture remains
    # explicit in the report and must not be conflated with endpoint success.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
