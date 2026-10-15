"""Entry point for the page: runs inside Pyodide in the visitor's browser (site/worker.js),
reads one ESPN league and builds the same two datasets the league site is made of.

    build(league_id, season, espn_s2, swid, relay, progress) -> JSON string:
        {"report": league/report.py's build_report, "live": league/live.py's build_live}
    live() -> JSON string: build_live again for the league ``build`` last read (the Live tab
        refreshes with this every few minutes)

``progress(text)``, if given, is called as the reads go by so the page can say what's happening.
"""

from __future__ import annotations

import json

import requests
from espn_api.requests import espn_requests

from league.espn import EspnClient
from league.live import build_live
from league.report import build_report

ESPN = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"


class _Http:
    """Stands in for the ``requests`` module inside espn-api. A browser can't send cookies to
    another site, so a request that carries them goes to our relay with them as headers
    (functions/api/espn); one without (a public league) goes straight to ESPN."""

    def __init__(self, relay: str, progress=None):
        self.relay = relay
        self.progress = progress
        self.count = 0
        self.session = requests.Session()
        for h in ("Accept-Encoding", "Connection"):  # the browser sets these; asking logs errors
            self.session.headers.pop(h, None)

    def get(self, url, params=None, headers=None, cookies=None, **kw):
        headers = dict(headers or {})
        if cookies and cookies.get("espn_s2") and url.startswith(ESPN):
            url = self.relay + url.removeprefix(ESPN)
            headers["x-espn-s2"] = cookies["espn_s2"]
            headers["x-espn-swid"] = cookies["SWID"]
        self.count += 1
        if self.progress:
            self.progress(f"Reading your league from ESPN ({self.count})…")
        return self.session.get(url, params=params, headers=headers, **kw)


_client: EspnClient | None = None


def build(league_id, season, espn_s2=None, swid=None, relay="/api/espn/", progress=None) -> str:
    global _client
    espn_requests.requests = _Http(relay, progress)
    _client = EspnClient(league_id, season, espn_s2, swid)
    report = build_report(_client, progress=progress)
    if progress:
        progress("Checking this week's games…")
    try:  # the season report stands on its own; a live-scores hiccup shouldn't sink it
        live = build_live(_client)
    except Exception:  # noqa: BLE001
        live = None
    espn_requests.requests.progress = None  # the page's callback is only good for this call
    return json.dumps({"report": report, "live": live}, separators=(",", ":"))


def live() -> str:
    """This week's lineups again, for the league ``build`` last read."""
    if _client is None:
        raise RuntimeError("No league loaded yet.")
    return json.dumps(build_live(_client), separators=(",", ":"))
