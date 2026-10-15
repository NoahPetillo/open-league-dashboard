# Open League Dashboard

Standings and power rankings for any ESPN fantasy football league. Enter a league ID and
the stats are computed right in your browser. No account, no database, nothing saved on a
server.

## How it works

- `site/` is a static page. A Web Worker loads [Pyodide](https://pyodide.org) (Python
  compiled to WebAssembly) and runs the Python in `league/` and `py/browser.py`, reading the
  league through [espn-api](https://github.com/cwendt94/espn-api).
- **Public leagues** load straight from ESPN, which allows requests from any site. No server
  is involved.
- **Private leagues** need the `espn_s2` and `SWID` cookies from a logged-in ESPN session.
  Browsers won't let a page attach cookies for another site, so the page sends them as
  headers to a small relay (`functions/api/espn/`, a Cloudflare Pages Function), which turns
  them back into cookies for ESPN. The relay stores and logs nothing, and it can only reach
  ESPN's fantasy football read API. Read it: it's about 40 lines.
- **Easier option for private leagues:** a league manager can turn on ESPN's setting that
  makes the league viewable to the public. Then nobody needs cookies.

Cookies and the league ID are saved in your browser only when you tick "Remember on this
device".

## Power rankings

A 0–100 score after every completed regular-season week:

- 50% all-play record (your score against every other team's score that week)
- 30% scoring over the last three weeks, scaled across the league
- 20% actual record

Each team also gets a one-line note about its most notable fact that week. The full rules
are in `league/power.py`.

## Running it locally

Needs [uv](https://docs.astral.sh/uv/) and Node 22+.

```
uv sync
npm install
npm run dev        # builds site/py/bundle.zip, then serves http://localhost:8789
uv run pytest
```

`npm run build` packages `py/browser.py`, `league/` and the football part of espn-api into
`site/py/bundle.zip`, which the page downloads. Run it again after changing any Python.

## Hosting

Any Cloudflare Pages project works (free plan): build with `npm run build`, output directory
`site`, and the relay deploys from `functions/` automatically. Or from your machine:

```
npx wrangler pages project create open-league-dashboard --production-branch main
npm run build && npx wrangler pages deploy
```

The free plan allows 100,000 relay requests a day, and loading a private league uses about
four. Public leagues don't use the relay at all.

A visitor's first load downloads about 6 MB (Python itself) from the jsDelivr CDN. After
that their browser caches it.

## License

MIT. See `LICENSE`.
