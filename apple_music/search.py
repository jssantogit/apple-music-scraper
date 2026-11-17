"""/apple-music/search/* — autocomplete, all-types search and one paged
search per resource type."""
from apple_music import parsers as P
from apple_music import refs
from apple_music.fetch import AppleMusicUpstreamError, api_get, catalog_get, run_parallel
from apple_music.shared import storefront
from urllib.parse import parse_qsl, urlsplit


def auto_complete(query, country=None, lang=None):
    """Search-box suggestions: completed terms plus the top matching items."""
    sf = storefront(country)
    body = catalog_get(sf, "search/suggestions", {
        "term": query, "kinds": "terms,topResults", "types": refs.SUGGESTION_TYPES, "limit": 10,
    }, lang=lang)
    suggestions = ((body or {}).get("results") or {}).get("suggestions") or []
    terms = [s.get("displayTerm") or s.get("searchTerm") for s in suggestions
             if s.get("kind") == "terms" and (s.get("displayTerm") or s.get("searchTerm"))]
    top = [s.get("content") for s in suggestions if s.get("kind") == "topResults" and s.get("content")]
    return {"query": query, "suggestions": terms, "top_results": P.items(top, typed=True)}


def _block(body, kind):
    return (((body or {}).get("results") or {}).get(kind) or {})


def search_all(query, limit=5, country=None, lang=None):
    """Every result type at once: top results + the first `limit` of each."""
    sf = storefront(country)

    def core():
        return catalog_get(sf, "search", {"term": query, "types": ",".join(refs.SEARCH_ALL_CORE),
                                          "limit": limit, "with": "topResults"}, lang=lang)

    def extra():
        return catalog_get(sf, "search", {"term": query, "types": ",".join(refs.SEARCH_ALL_EXTRA),
                                          "limit": limit}, lang=lang)

    main, more = run_parallel([core, extra])
    # API relationships can be explicitly null, not just absent.
    curators = (_block(more, "apple-curators").get("data") or []) + (
        _block(more, "curators").get("data") or []
    )
    return {
        "query": query,
        "top_results": P.items(_block(main, "topResults").get("data"), typed=True),
        "songs": P.items(_block(main, "songs").get("data")),
        "albums": P.items(_block(main, "albums").get("data")),
        "artists": P.items(_block(main, "artists").get("data")),
        "playlists": P.items(_block(main, "playlists").get("data")),
        "music_videos": P.items(_block(more, "music-videos").get("data")),
        "stations": P.items(_block(more, "stations").get("data")),
        "curators": P.items(curators[:limit]),
        "labels": P.items(_block(more, "record-labels").get("data")),
    }


def _next_search_block(sf, kind, cursor, limit, lang, seen):
    """Follow only an Apple-issued cursor for this storefront and resource."""
    if cursor in seen:
        raise AppleMusicUpstreamError("cyclic Apple Music search cursor")
    seen.add(cursor)
    parsed = urlsplit(cursor)
    if (parsed.path != f"/v1/catalog/{sf}/search" or
            parsed.scheme not in ("", "https") or
            parsed.netloc not in ("", "amp-api.music.apple.com")):
        raise AppleMusicUpstreamError("invalid Apple Music search cursor")
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if not params:
        raise AppleMusicUpstreamError("empty Apple Music search cursor")
    # The upstream cursor encodes ranking-offset internals; never replace it
    # with page*limit. The cursor often omits limit, which defaults to 5.
    params["limit"] = limit
    return _block(api_get(parsed.path, params, lang=lang), kind)


def _collect_type(sf, query, kind, limit, target, lang):
    """Read up to target results through this type's independent cursor.

    Returns (resources, has_more) without inventing a numeric offset. A
    combined curator search may request only part of the last batch.
    """
    body = catalog_get(sf, "search", {"term": query, "types": kind, "limit": limit},
                       lang=lang)
    block, seen, rows = _block(body, kind), set(), []
    while True:
        data = block.get("data") or []
        if not isinstance(data, list):
            raise AppleMusicUpstreamError("search results must contain a list")
        remaining = target - len(rows)
        rows.extend(data[:remaining])
        more = bool(block.get("next")) or len(data) > remaining
        if len(rows) >= target:
            return rows, more
        cursor = block.get("next")
        if not cursor:
            return rows, False
        if not data:
            raise AppleMusicUpstreamError("non-progressing Apple Music search cursor")
        block = _next_search_block(sf, kind, cursor, limit, lang, seen)


def _typed_search(kind):
    types = refs.SEARCH_TYPES[kind]
    out_key = kind.replace("-", "_")

    def search(query, page=1, limit=25, country=None, lang=None):
        sf = storefront(country)
        start, end = (page - 1) * limit, page * limit
        rows, has_more = [], False
        # Each catalog resource type has an independent search cursor. Treat
        # them as an ordered combined stream, bounded by the caller's limit.
        for i, resource_type in enumerate(types):
            to_read = end - len(rows)
            if to_read <= 0:
                break
            batch, type_has_more = _collect_type(
                sf, query, resource_type, limit, to_read, lang,
            )
            rows.extend(batch)
            if len(rows) >= end:
                has_more = type_has_more
                if not has_more:
                    # At an exact type boundary, check if a later category
                    # contains anything before advertising a next page.
                    for following_type in types[i + 1:]:
                        peek, _ = _collect_type(sf, query, following_type, limit, 1, lang)
                        if peek:
                            has_more = True
                            break
                break
        return {"query": query, out_key: P.items(rows[start:end]),
                "pagination": P.pagination(page, limit, has_more)}

    search.__name__ = f"search_{out_key}"
    search.__doc__ = f"Paged {kind} search."
    return search


search_songs = _typed_search("songs")
search_albums = _typed_search("albums")
search_artists = _typed_search("artists")
search_playlists = _typed_search("playlists")
search_music_videos = _typed_search("music-videos")
search_stations = _typed_search("stations")
search_curators = _typed_search("curators")
search_labels = _typed_search("labels")
