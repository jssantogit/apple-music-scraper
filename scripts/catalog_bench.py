"""Rotating, fail-closed validation of the 51 Apple Music HTTP endpoints.

Offline tests cover request contracts. The live workbench is opt-in / scheduled,
reads only public metadata, and never writes raw Apple responses or tokens.
"""
import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import random
import re
import sys
import time
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import bottle

import routes
from schema_fields import load_query


# Every real endpoint has an explicit response contract. New routes must add one.
REQUIRED_RESPONSE_KEYS = {
    "/songs/details": ("id", "name", "artists"),
    "/songs/batch": ("songs", "not_found"),
    "/search/auto-complete": ("query", "suggestions", "top_results"),
    "/search/all": ("query", "songs", "albums", "artists", "playlists"),
    "/search/songs": ("query", "songs"),
    "/search/albums": ("query", "albums"),
    "/search/artists": ("query", "artists"),
    "/search/playlists": ("query", "playlists"),
    "/search/music-videos": ("query", "music_videos"),
    "/search/stations": ("query", "stations"),
    "/search/curators": ("query", "curators"),
    "/search/labels": ("query", "labels"),
    "/albums/details": ("id", "tracks", "artists"),
    "/albums/related": ("album", "other_versions", "more_by_artist"),
    "/artists/details": ("id", "name", "top_songs", "albums",
                         "singles_and_eps", "similar_artists"),
    "/artists/top-songs": ("artist_id", "songs"),
    "/artists/albums": ("artist_id", "albums", "type"),
    "/artists/music-videos": ("artist_id", "music_videos", "type"),
    "/artists/playlists": ("artist_id", "playlists", "type"),
    "/artists/similar": ("artist_id", "artists"),
    "/playlists/details": ("id", "tracks", "tracks_has_more"),
    "/playlists/tracks": ("playlist_id", "tracks"),
    "/music-videos/details": ("id", "name"),
    "/charts/top-songs": ("country", "songs"),
    "/charts/top-albums": ("country", "albums"),
    "/charts/top-playlists": ("country", "playlists"),
    "/charts/top-music-videos": ("country", "music_videos"),
    "/charts/daily-top-100": ("playlist", "songs", "region"),
    "/charts/daily-top-100-list": ("charts",),
    "/charts/city-top-25": ("playlist", "songs", "city"),
    "/charts/city-charts-list": ("charts",),
    "/browse": ("country", "sections", "explore_links"),
    "/browse/section": ("section", "items"),
    "/browse/new-releases": ("section", "items"),
    "/browse/recent-releases": ("section", "items"),
    "/browse/best-new-songs": ("section", "items"),
    "/browse/trending-songs": ("section", "items"),
    "/browse/coming-soon": ("section", "items"),
    "/browse/updated-playlists": ("section", "items"),
    "/browse/popular": ("section", "items"),
    "/browse/dj-mixes": ("section", "items"),
    "/radio": ("country", "sections"),
    "/stations/live": ("country", "stations"),
    "/stations/details": ("id", "name"),
    "/genres": ("country", "genres"),
    "/genres/details": ("genre", "sections"),
    "/labels/details": ("id", "latest_releases", "top_releases"),
    "/labels/releases": ("label_id", "albums", "type"),
    "/curators/details": ("id", "playlists", "sections"),
    "/curators/playlists": ("curator_id", "playlists"),
    "/countries": ("count", "countries"),
}

PAGINATED_PATHS = {
    path for path, _schema, _handler, paginated in routes.ENDPOINTS if paginated
}
SINGLE_ENTITY_PATHS = {
    "/songs/details", "/albums/details", "/artists/details",
    "/playlists/details", "/music-videos/details", "/stations/details",
    "/labels/details", "/curators/details",
}
# Empty editorial shelves can be legitimate; they are warnings, not hidden PASS.
OBSERVED_LIST = {
    "/songs/batch": "songs", "/search/all": "songs",
    "/search/auto-complete": "top_results",
    "/search/songs": "songs", "/search/albums": "albums",
    "/search/artists": "artists", "/search/playlists": "playlists",
    "/search/music-videos": "music_videos", "/search/stations": "stations",
    "/search/curators": "curators", "/search/labels": "labels",
    "/albums/details": "tracks", "/albums/related": "other_versions",
    "/artists/details": "top_songs", "/artists/top-songs": "songs",
    "/artists/albums": "albums", "/artists/music-videos": "music_videos",
    "/artists/playlists": "playlists", "/artists/similar": "artists",
    "/playlists/details": "tracks", "/playlists/tracks": "tracks",
    "/charts/top-songs": "songs", "/charts/top-albums": "albums",
    "/charts/top-playlists": "playlists", "/charts/top-music-videos": "music_videos",
    "/charts/daily-top-100": "songs", "/charts/daily-top-100-list": "charts",
    "/charts/city-top-25": "songs", "/charts/city-charts-list": "charts",
    "/browse": "sections", "/radio": "sections",
    "/stations/live": "stations", "/genres": "genres",
    "/genres/details": "sections", "/labels/details": "latest_releases",
    "/labels/releases": "albums", "/curators/details": "playlists",
    "/curators/playlists": "playlists", "/countries": "countries",
}
for _path in REQUIRED_RESPONSE_KEYS:
    if _path.startswith("/browse/") and _path not in OBSERVED_LIST:
        OBSERVED_LIST[_path] = "items"


class FixtureMissing(ValueError):
    """A valid resource could not be discovered for an endpoint."""


def read_case_pool(path=None):
    path = Path(path) if path else Path(__file__).with_name("catalog_bench_cases.json")
    pool = json.loads(path.read_text(encoding="utf-8"))
    portfolios = pool.get("portfolios")
    if not isinstance(portfolios, list) or not portfolios:
        raise ValueError("case pool has no portfolios")
    for portfolio in portfolios:
        if not isinstance(portfolio, dict) or not portfolio.get("query"):
            raise ValueError("each portfolio requires a nonempty search query")
    return pool


def choose_portfolio(pool, seed):
    """Portable modulo rotation. Record the seed to replay any run."""
    return pool["portfolios"][int(seed) % len(pool["portfolios"])]


def _pick(seed, path, values):
    return random.Random(f"{seed}:{path}").choice(list(values))


def _need(context, field):
    result = context.get(field)
    if not result:
        raise FixtureMissing(f"missing discovered {field} fixture")
    return result


def case_for(path, context, *, country, term, seed=0):
    """Build valid request args from discovered IDs, not a fixed song/artist."""
    if path not in REQUIRED_RESPONSE_KEYS:
        raise ValueError(f"endpoint not mapped: {path}")
    lang_only = ("/countries", "/charts/daily-top-100",
                 "/charts/daily-top-100-list", "/charts/city-top-25",
                 "/charts/city-charts-list")
    params = {"lang": "en-US"}
    if path not in lang_only:
        params["country"] = country
    page_size = str(_pick(seed, path, (2, 4, 6)))

    if path.startswith("/search/"):
        params["query"] = term
        if path not in ("/search/all", "/search/auto-complete"):
            params.update(page="1", limit=page_size)
        elif path == "/search/all":
            params["limit"] = page_size
    elif path == "/songs/details":
        params["song"] = _need(context, "song")
    elif path == "/songs/batch":
        params["songs"] = ",".join(_need(context, "songs")[:3])
    elif path.startswith("/albums/"):
        params["album"] = _need(context, "album")
    elif path.startswith("/artists/"):
        params["artist"] = _need(context, "artist")
        if path != "/artists/details":
            params.update(page="1", limit=page_size)
        if path == "/artists/albums":
            params["type"] = _pick(seed, path, (
                "all", "albums", "singles", "live", "compilations",
                "appears-on", "essential"))
        if path == "/artists/music-videos":
            params["type"] = _pick(seed, path, ("all", "top"))
        if path == "/artists/playlists":
            params["type"] = _pick(seed, path, ("artist", "featured"))
    elif path.startswith("/playlists/"):
        params["playlist"] = _need(context, "playlist")
        if path.endswith("/tracks"):
            params.update(page="1", limit=page_size)
    elif path == "/music-videos/details":
        params["video"] = _need(context, "video")
    elif path.startswith("/charts/top-"):
        params.update(page="1", limit=page_size)
        # A seed rotates between global and a genre-specific chart.
        if int(seed) % 3 == 1:
            params["genre"] = _need(context, "genre")
    elif path == "/charts/daily-top-100":
        params["region"] = _need(context, "region")
    elif path == "/charts/city-top-25":
        params["city"] = _need(context, "city")
    elif path.startswith("/browse/"):
        params.update(page="1", limit=page_size)
        if path == "/browse/section":
            params["section"] = _need(context, "section")
        if int(seed) % 2 == 1:
            params["sort"] = _pick(seed, path, ("featured", "name"))
    elif path == "/genres/details":
        params["genre"] = _need(context, "genre")
    elif path.startswith("/labels/"):
        params["label"] = _need(context, "label")
        if path == "/labels/releases":
            params.update(page="1", limit=page_size,
                          type=_pick(seed, path, ("latest", "top")))
    elif path.startswith("/curators/"):
        params["curator"] = _need(context, "curator")
        if path == "/curators/playlists":
            params.update(page="1", limit=page_size)
    elif path == "/stations/details":
        params["station"] = _need(context, "station")
    return params


def wsgi_get(path, params=None):
    """Exercise the real Bottle route and Marshmallow schema without a port."""
    env = {}
    setup_testing_defaults(env)
    env["REQUEST_METHOD"] = "GET"
    env["PATH_INFO"] = path
    env["QUERY_STRING"] = urlencode(params or {}, doseq=True)
    env["HTTP_HOST"] = "127.0.0.1:8000"
    env["wsgi.input"] = io.BytesIO(b"")
    captured = {}

    def response(status, headers, exc_info=None):
        captured["status"] = int(status.split()[0])

    result = bottle.default_app()(env, response)
    try:
        body = b"".join(result)
    finally:
        if hasattr(result, "close"):
            result.close()
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        payload = {"_unparseable_json": True}
    return captured["status"], payload


def validate_result(path, status, payload, params):
    if status != 200:
        return {"result": "fail", "reason": f"HTTP {status}"}
    if not isinstance(payload, dict):
        return {"result": "fail", "reason": "response is not a JSON object"}
    required = REQUIRED_RESPONSE_KEYS.get(path)
    if not required:
        return {"result": "fail", "reason": "unregistered response contract"}
    missing = [key for key in required if key not in payload]
    if missing:
        return {"result": "fail", "reason": "missing fields: " + ", ".join(missing)}
    if path in SINGLE_ENTITY_PATHS and (not payload.get("id") or not payload.get("name")):
        return {"result": "fail", "reason": "missing nonempty identity id/name"}
    if path in PAGINATED_PATHS:
        if not isinstance(payload.get("current_page"), int):
            return {"result": "fail", "reason": "missing numeric current_page"}
        if payload["current_page"] != int(params.get("page", 1)):
            return {"result": "fail", "reason": "page number mismatch"}
        if not isinstance(payload.get("per_page"), int) or payload["per_page"] <= 0:
            return {"result": "fail", "reason": "missing positive per_page"}
    list_field = OBSERVED_LIST.get(path)
    if list_field is not None:
        values = payload.get(list_field)
        if not isinstance(values, list):
            return {"result": "fail", "reason": f"{list_field} is not a list"}
        if any(not isinstance(item, dict) for item in values):
            return {"result": "fail", "reason": f"{list_field} includes non-object items"}
        if not values:
            return {"result": "warn", "reason": f"empty {list_field}", "observed_count": 0}
        return {"result": "pass", "reason": "", "observed_count": len(values)}
    return {"result": "pass", "reason": "", "observed_count": None}


def safe_error(message):
    """Never export bearer tokens / JWTs in CI logs."""
    text = str(message)
    text = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                  "[redacted jwt]", text)
    text = re.sub(r"(?i)Bearer\s+\S+", "Bearer [redacted]", text)
    return text[:180]


def summarize(rows, *, expected_routes, strict_empty=False):
    actual = {row["path"] for row in rows}
    uncovered = sorted(set(expected_routes) - actual)
    failed = sum(1 for row in rows if row["result"] in ("fail", "blocked"))
    warned = sum(1 for row in rows if row["result"] == "warn")
    return {
        "covered": len(actual & set(expected_routes)),
        "total_endpoints": len(expected_routes),
        "uncovered": uncovered,
        "cases": len(rows),
        "failed_cases": failed,
        "warning_cases": warned,
        "passed": not uncovered and failed == 0 and (not strict_empty or warned == 0),
    }


def _entries(payload, key):
    entries = payload.get(key) or []
    return [entry for entry in entries
            if isinstance(entry, dict) and entry.get("id")]


def _candidate_id(entries, seed, tag):
    if not entries:
        return None
    return str(_pick(seed, tag, entries).get("id"))


def discover(country, term, seed, pool):
    """Prefer newly discovered resources. Explicit fallback IDs are a last resort.

    Discovery failures are recorded; missing fixtures subsequently fail
    their endpoints rather than reporting a false green status.
    """
    source = {}
    issues = []

    def get(path, params):
        try:
            status, payload = wsgi_get(path, params)
            if status == 200 and isinstance(payload, dict):
                return payload
            issues.append({"path": path, "http_status": status})
        except Exception as exc:
            issues.append({"path": path, "error": safe_error(exc)})
        return {}

    base = {"country": country, "lang": "en-US"}
    found = get("/search/all", {**base, "query": term, "limit": "10"})
    ctx = {}
    selected = {
        "song": ("songs",),
        "album": ("albums",),
        "artist": ("artists",),
        "playlist": ("playlists",),
        "video": ("music_videos",),
        "station": ("stations",),
        "curator": ("curators",),
        "label": ("labels",),
    }
    for key, (collection,) in selected.items():
        identifier = _candidate_id(_entries(found, collection), seed, key)
        if identifier:
            ctx[key], source[key] = identifier, "search/all"

    song_ids = [str(item["id"]) for item in _entries(found, "songs")]
    ctx["songs"] = list(dict.fromkeys(song_ids))[:3]
    if not ctx["songs"] and ctx.get("song"):
        ctx["songs"] = [ctx["song"]]

    extra = {
        "playlist": ("/search/playlists", "playlists"),
        "video": ("/search/music-videos", "music_videos"),
        "label": ("/search/labels", "labels"),
        "curator": ("/search/curators", "curators"),
        "station": ("/stations/live", "stations"),
    }
    for key, (path, collection) in extra.items():
        if key in ctx:
            continue
        args = dict(base)
        if path.startswith("/search/"):
            args.update(query=term, limit="5")
        payload = get(path, args)
        identifier = _candidate_id(_entries(payload, collection), seed, path)
        if identifier:
            ctx[key], source[key] = identifier, path

    genres = get("/genres", base)
    ctx["genre"] = _candidate_id(_entries(genres, "genres"), seed, "genre")
    if ctx["genre"]:
        source["genre"] = "/genres"

    browse = get("/browse", base)
    room_ids = [str(s["see_all_id"]) for s in browse.get("sections", [])
                if isinstance(s, dict) and s.get("see_all_id")
                and re.fullmatch(r"\d{4,12}", str(s["see_all_id"]))]
    if room_ids:
        ctx["section"] = _pick(seed, "section", room_ids)
        source["section"] = "/browse"

    city_list = get("/charts/city-charts-list", {"lang": "en-US"})
    cities = [s.get("city") for s in city_list.get("charts", [])
              if isinstance(s, dict) and s.get("city")]
    if cities:
        ctx["city"] = _pick(seed, "city", cities)
        source["city"] = "/charts/city-charts-list"

    top_list = get("/charts/daily-top-100-list", {"lang": "en-US"})
    regions = [str(s["country_code"]).lower()
               for s in top_list.get("charts", [])
               if isinstance(s, dict) and s.get("country_code")]
    ctx["region"] = _pick(seed, "region", regions) if regions else "global"
    source["region"] = "/charts/daily-top-100-list" if regions else "default"

    for key, options in pool.get("fallback_ids", {}).items():
        if not ctx.get(key) and options:
            ctx[key] = _pick(seed, f"fallback:{key}", options)
            source[key] = "documented-fallback"

    return ctx, source, issues


def run_one(path, params, *, country, profile, seed):
    started = time.monotonic()
    try:
        status, data = wsgi_get(path, params)
        checked = validate_result(path, status, data, params)
    except Exception as exc:
        status = None
        checked = {"result": "fail", "reason": "exception: " + safe_error(exc)}
    elapsed = round((time.monotonic() - started) * 1000)
    return {
        "path": path, "country": country, "profile": profile, "seed": seed,
        "result": checked["result"], "reason": checked["reason"],
        "http_status": status, "elapsed_ms": elapsed,
        "observed_count": checked.get("observed_count"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None,
                        help="Reproduction seed; defaults to GITHUB_RUN_NUMBER")
    parser.add_argument("--storefronts", default="br,us,gb,jp,in,fr",
                        help="Comma-separated candidate storefronts")
    parser.add_argument("--profile", choices=("standard", "deep"), default="standard")
    parser.add_argument("--query", default="", help="Override rotating search query")
    parser.add_argument("--case-pool", default="", help="Versioned JSON portfolios file")
    parser.add_argument("--strict-empty", action="store_true")
    parser.add_argument("--delay", type=float, default=0.4,
                        help="Seconds between endpoint calls to reduce load")
    parser.add_argument("--output", default="catalog-bench-report.json")
    args = parser.parse_args(argv)
    if args.delay < 0.1 or args.delay > 10:
        parser.error("--delay must be between 0.1 and 10 seconds")
    seed = args.seed if args.seed is not None else int(os.getenv("GITHUB_RUN_NUMBER", "0"))
    try:
        pool = read_case_pool(args.case_pool or None)
        portfolio = choose_portfolio(pool, seed)
        term = args.query.strip() or portfolio["query"]
        countries = [s.strip().lower() for s in args.storefronts.split(",") if s.strip()]
        if not countries or len(set(countries)) != len(countries) or any(
            not re.fullmatch(r"[a-z]{2}", s) for s in countries
        ):
            parser.error("storefronts must be unique two-letter country codes")
    except (ValueError, OSError) as e:
        parser.error(safe_error(e))
    selected = []
    count = 1 if args.profile == "standard" else min(2, len(countries))
    for index in range(count):
        selected.append(countries[(seed + index) % len(countries)])

    expected = set(REQUIRED_RESPONSE_KEYS)
    actual = {path for path, _schema, _handler, _paginated in routes.ENDPOINTS}
    if actual != expected:
        print("FAILED: route inventory mismatch", file=sys.stderr)
        return 2

    rows, fixture_sources, discovery_issues = [], {}, {}
    started_at = datetime.now(timezone.utc).isoformat()
    for country in selected:
        ctx, sources, issues = discover(country, term, seed, pool)
        fixture_sources[country] = sources
        discovery_issues[country] = issues
        for path, schema, _handler, _paginated in routes.ENDPOINTS:
            try:
                params = case_for(path, ctx, country=country, term=term, seed=seed)
                _, error = load_query(schema, params)
                if error:
                    raise ValueError(f"fixture fails query validation: {error}")
                row = run_one(path, params, country=country, profile=args.profile, seed=seed)
            except Exception as e:
                row = {
                    "path": path, "country": country, "profile": args.profile, "seed": seed,
                    "result": "blocked", "reason": safe_error(e),
                    "http_status": None, "elapsed_ms": 0, "observed_count": None,
                }
            rows.append(row)
            print(f'{country.upper()} {row["result"].upper():7s} '
                  f'{path:32s} {row["elapsed_ms"]:5d}ms {row["reason"]}',
                  flush=True)
            time.sleep(args.delay)
    overview = summarize(rows, expected_routes=expected, strict_empty=args.strict_empty)
    overview["countries"] = selected
    overview["seed"] = seed
    overview["portfolio"] = portfolio["name"]
    overview["search_query"] = term
    overview["observed_at_utc"] = started_at
    # Case identities, public IDs and presence only. Never dump raw payloads.
    overview["fixture_sources"] = fixture_sources
    overview["discovery_issues"] = discovery_issues
    overview["results"] = rows
    Path(args.output).write_text(json.dumps(overview, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    summary = [
        "## Catalog validation workbench",
        "",
        f'Seed: {seed}; portfolio: {portfolio["name"]}; query: {term}; countries: {", ".join(selected)}',
        f'Coverage: {overview["covered"]}/{overview["total_endpoints"]} routes; '
        f'cases: {overview["cases"]}; failed: {overview["failed_cases"]}; '
        f'warnings: {overview["warning_cases"]}.',
        "",
        "| Country | Endpoint | Result | HTTP | Time | Note |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        summary.append(
            f'| {row["country"].upper()} | {row["path"]} | {row["result"]} | '
            f'{row["http_status"] or "-"} | {row["elapsed_ms"]} ms | '
            f'{row["reason"].replace("|", "/")} |'
        )
    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write("\n".join(summary) + "\n")
    print(f'BENCH result={"PASS" if overview["passed"] else "FAIL"}; '
          f'coverage={overview["covered"]}/{overview["total_endpoints"]}; '
          f'failed={overview["failed_cases"]}; warnings={overview["warning_cases"]}')
    return 0 if overview["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
