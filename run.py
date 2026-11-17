"""Start the Apple Music Scraper API.

    python run.py                        # http://127.0.0.1:8000
    PORT=9000 python run.py              # another port
    HOST=0.0.0.0 python run.py            # explicit LAN access

Then:  curl "http://localhost:8000/songs/details?song=1649434293"
"""
import bottle
from cheroot import wsgi

import config
import routes  # noqa: F401  (mounts the routes on bottle's default app)


def main():
    app = bottle.default_app()
    print(f"Apple Music Scraper listening on http://{config.HOST}:{config.PORT}/")
    print(f"Try:  curl \"http://localhost:{config.PORT}/songs/details?song=1649434293\"")
    server = wsgi.Server((config.HOST, config.PORT), app, server_name="apple-music-scraper", numthreads=16)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
