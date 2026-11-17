"""Public HTTP route contract checks; intentionally no live Apple requests."""

import bottle
import pytest

import routes
from apple_music import refs


def test_51_documented_endpoints_have_unique_paths_and_callable_handlers():
    assert len(routes.ENDPOINTS) == 51
    paths = [path for path, _schema, _handler, _paged in routes.ENDPOINTS]
    assert len(paths) == len(set(paths))
    assert all(path.startswith("/") for path in paths)
    assert all(callable(handler) for _path, _schema, handler, _paged in routes.ENDPOINTS)


def test_every_endpoint_supports_both_short_and_prefixed_paths():
    registered = {(route.rule, route.method) for route in bottle.default_app().routes}
    for path, _schema, _handler, _paged in routes.ENDPOINTS:
        assert (path, "GET") in registered, path
        assert ("/apple-music" + path, "GET") in registered, path
    assert ("/health", "GET") in registered


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1649434293", {"id": "1649434293", "country": None}),
        (
            "https://music.apple.com/br/album/anti-hero/1649434004?i=1649434293",
            {"id": "1649434293", "country": "br"},
        ),
        ("USUG12205736", {"isrc": "USUG12205736"}),
    ],
)
def test_song_identity_resolver_preserves_id_isrc_and_storefront(value, expected):
    assert refs.resolve_song(value) == expected


def test_album_barcode_is_not_misclassified_as_catalog_id():
    assert refs.resolve_album("00602448762689") == {"upc": "00602448762689"}
