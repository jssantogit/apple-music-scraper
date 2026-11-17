"""Small, explicit live read-only Apple catalog probe.

This is NOT part of the offline test suite. Run manually when you wish to
check what anonymous storefront endpoints actually return today:

    python -m scripts.catalog_live_probe --countries br us

It queries only public catalog metadata and prints a small presence/count
report: no raw payloads, access tokens, previews, lyrics, or full audio.
"""
import argparse
from datetime import datetime, timezone
import json

from apple_music import albums, artists, search, songs


def choose_entity(rows):
    """Pick a usable search result; never assume the first result is complete."""
    return next(
        (row for row in rows or []
         if isinstance(row, dict) and row.get("id") and row.get("name")),
        None,
    )


def summarize_country(country, artist, album, song):
    """State only observable metadata. Trait flags are not audio access."""
    return {
        "country": country.upper(),
        "artist": {
            "id": artist.get("id"),
            "top_songs_count": len(artist.get("top_songs") or []),
            "albums_count": len(artist.get("albums") or []),
            "singles_and_eps_count": len(artist.get("singles_and_eps") or []),
            "similar_artists_count": len(artist.get("similar_artists") or []),
            "artwork_url_present": bool((artist.get("artwork") or {}).get("link")),
        },
        "album": {
            "id": album.get("id"),
            "track_count_observed": len(album.get("tracks") or []),
            "has_upc": bool(album.get("upc")),
            "artwork_url_present": bool((album.get("artwork") or {}).get("link")),
        },
        "song": {
            "id": song.get("id"),
            "has_isrc": bool(song.get("isrc")),
            "has_preview_url": bool(song.get("preview_link")),
            # The anonymous catalog endpoint does not supply playback access.
            "has_full_stream": False,
        },
    }


def probe(country, term):
    """Four bounded catalog operations (search_all fans out to two requests)."""
    found = search.search_all(term, limit=3, country=country, lang="en-US")
    picks = {kind: choose_entity(found.get(kind)) for kind in ("artists", "albums", "songs")}
    missing = [kind for kind, item in picks.items() if item is None]
    if missing:
        raise ValueError(f"{country.upper()} search has no usable {', '.join(missing)} result")

    artist = artists.details({"id": picks["artists"]["id"], "country": country},
                             country=country, lang="en-US")
    album = albums.details({"id": picks["albums"]["id"], "country": country},
                           country=country, lang="en-US")
    song = songs.details({"id": picks["songs"]["id"], "country": country},
                         country=country, lang="en-US")
    for kind, record, pick in (
        ("artist", artist, picks["artists"]),
        ("album", album, picks["albums"]),
        ("song", song, picks["songs"]),
    ):
        if str(record.get("id")) != str(pick["id"]):
            raise ValueError(f"{country.upper()} {kind} detail id differs from search result")

    return summarize_country(country, artist, album, song)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countries", nargs="+", choices=("br", "us"),
                        default=["br", "us"], help="Explicit storefronts to inspect")
    parser.add_argument("--term", default="Daft Punk",
                        help="Public catalog search query; default: Daft Punk")
    args = parser.parse_args(argv)
    if len(args.countries) > 2 or len(set(args.countries)) != len(args.countries):
        parser.error("choose at most two distinct storefronts")

    report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "query": args.term, "countries": []}
    for country in args.countries:
        report["countries"].append(probe(country, args.term))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
