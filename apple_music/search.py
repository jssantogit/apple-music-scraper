"""/apple-music/search/* — autocomplete, all-types search and one paged
search per resource type."""
from apple_music import parsers as P
from apple_music import refs
from apple_music.fetch import AppleMusicUpstreamError, api_get, catalog_get, run_parallel
from apple_music.shared import offset_of, storefront
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


def _follow_single_search_type(sf, query, kind, page, limit, lang):
    """Follow upstream's own search result cursor instead of guessing offset.

    amp-api/search may count additional internal ranking entries when it
    advances a cursor. Its next offset is not necessarily page * limit.
    """
    body = catalog_get(sf, "search", {
        "term": query, "types": kind, "limit": limit,
    }, lang=lang)
    block = _block(body, kind)
    seen = set()
    for _ in range(1, page):
        cursor = block.get("next")
        if not cursor:
            return {}
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
        # The returned next URL often omits limit and defaults to 5 items.
        params["limit"] = limit
        body = api_get(parsed.path, params, lang=lang)
        block = _block(body, kind)
    return block


def _typed_search(kind):
    types = refs.SEARCH_TYPES[kind]
    out_key = kind.replace("-", "_")

    def search(query, page=1, limit=25, country=None, lang=None):
        sf = storefront(country)
        if len(types) == 1:
            block = _follow_single_search_type(sf, query, types[0], page, limit, lang)
            data = block.get("data") or []
            has_more = bool(block.get("next"))
        else:
            # Curators join apple-curators and curators; their separate
            # cursor streams require a dedicated combined-page policy.
            body = catalog_get(sf, "search", {
                "term": query, "types": ",".join(types), "limit": limit,
                "offset": offset_of(page, limit) or None,
            }, lang=lang)
            data, has_more = [], False
            for t in types:
                block = _block(body, t)
                data.extend(block.get("data") or [])
                has_more = has_more or bool(block.get("next"))
        return {"query": query, out_key: P.items(data),
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
