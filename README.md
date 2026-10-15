# Open League Dashboard

A full stats dashboard for any ESPN fantasy football league. Enter a league ID and
everything is computed right in your browser. No account, no database, nothing saved on a
server.

## What's in it

- **Home:** power rankings with a note on each team, headline tiles, the most-traded players,
  and a Sunday recap of how each matchup's win chances moved
- **Live:** this week's lineups and scores (refreshed every 5 minutes) and an upset alert
- **Standings:** all-play records and luck, a schedule swap grid, and strength of schedule ahead
- **Odds:** playoff, bye and last-place odds from 10,000 simulated seasons, how they've moved,
  and clinching scenarios
- **Managers:** a page per manager, with a manager style
- **Rivalries:** head-to-head records, including past seasons ESPN still has
- **Draft:** every pick graded, team report cards
- **Trades:** every trade graded for both sides, who wins the trade market, trade offers,
  the trade tree and trade regret
- **Waivers:** FAAB report card, drops that got away, ride-or-die players and every add/drop
- **Lineups:** lineup efficiency, points left on the bench, records with perfect lineups,
  weekly score heatmap
- **Awards:** weekly awards and streaks
- **Settings:** R-rated mode (off by default; turns on cruder names for a couple of things)
  and whether this device remembers the league

Some public leagues keep their adds, drops and trades to members. For those, everything
except trades and waivers works without cookies, and the page says so.

## How it works

- `site/` is a static page. A Web Worker (`site/worker.js`) loads [Pyodide](https://pyodide.org)
  (Python compiled to WebAssembly) and runs `py/browser.py`, which reads the league through
  [espn-api](https://github.com/cwendt94/espn-api) and builds the report with `league/`.
  `site/start.js` then hands the result to the dashboard's tabs in `site/app/`.
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

## How the numbers work

Each feature is one module in `league/`, built from the context `league/report.py` reads
from ESPN, with its method in the module's docstring. For example, power rankings
(`league/power.py`) are 50% all-play record, 30% the last three weeks of scoring and 20%
actual record, and the odds (`league/punishment.py`) simulate the rest of the regular season
10,000 times on ESPN's real schedule. Playoff seeding follows ESPN's rules and the league's
own settings: the number of playoff teams, division winners first (in leagues with
divisions), then the best records. Ties go to the league's chosen tiebreaker first, then
the rest of ESPN's order (head-to-head, points for, division record, points against), then a
coin flip.

The first visit downloads about 6 MB (Python itself) from the jsDelivr CDN, and the browser
caches it after that. Reading a league takes 30 to 100 requests to ESPN depending on how far
the season has gone, so a load takes roughly 10 to 30 seconds.

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

Live at https://open-league-dashboard.pages.dev, on Cloudflare Pages (free plan). The relay
deploys from `functions/` along with the site.

**Deploys.** Every push to `main` runs `.github/workflows/deploy.yml`: lint and tests, then it
builds the bundle and publishes to the `open-league-dashboard` Pages project. Pull requests
only run the tests. It needs two repository secrets (Settings → Secrets and variables →
Actions):

- `CLOUDFLARE_API_TOKEN`: a Cloudflare API token with **Account → Cloudflare Pages → Edit**
- `CLOUDFLARE_ACCOUNT_ID`: the Cloudflare account the project lives in

To deploy by hand, or to host your own copy:

```
npx wrangler pages project create open-league-dashboard --production-branch main
npm run build && npx wrangler pages deploy --branch main
```

The free plan allows 100,000 relay requests a day, and loading a private league uses about
four. Public leagues don't use the relay at all.

## License

MIT. See `LICENSE`.
