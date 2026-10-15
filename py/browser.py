"""Entry point for the open dashboard: runs inside Pyodide in the visitor's browser
(site/worker.js), reads one ESPN league and builds standings + power rankings with
the same league/ code the league site uses.

    build(league_id, season, espn_s2, swid, relay) -> JSON string:
    {"league": {...}, "teams": [standings rows], "power": power.build(...)}

Everything comes from espn-api's ``League`` load (a handful of requests); no box scores.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import requests
from espn_api.requests import espn_requests

from league import power

ESPN = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"


class _Http:
    """Stands in for the ``requests`` module inside espn-api. A browser can't send cookies to
    another site, so a request that carries them goes to our relay with them as headers
    (functions/api/espn); one without (a public league) goes straight to ESPN."""

    def __init__(self, relay: str):
        self.relay = relay
        self.session = requests.Session()
        for h in ("Accept-Encoding", "Connection"):  # the browser sets these; asking logs errors
            self.session.headers.pop(h, None)

    def get(self, url, params=None, headers=None, cookies=None, **kw):
        headers = dict(headers or {})
        if cookies and cookies.get("espn_s2") and url.startswith(ESPN):
            url = self.relay + url.removeprefix(ESPN)
            headers["x-espn-s2"] = cookies["espn_s2"]
            headers["x-espn-swid"] = cookies["SWID"]
        return self.session.get(url, params=params, headers=headers, **kw)


def _braced(swid: str | None) -> str | None:
    """SWID wrapped in braces, which ESPN expects (people often copy it without)."""
    s = (swid or "").strip()
    if not s:
        return None
    return ("" if s.startswith("{") else "{") + s + ("" if s.endswith("}") else "}")


def _matchups(lg, through: int) -> dict[int, list[dict]]:
    """Every completed week's games, in the shape power.build reads: week → [{home, away,
    home_score, away_score}]. A team's schedule/scores lists are indexed by week."""
    by_id = {t.team_id: t for t in lg.teams}
    out: dict[int, list[dict]] = {}
    for w in range(1, through + 1):
        out[w] = []
        for t in lg.teams:
            if w > len(t.schedule) or w > len(t.scores):
                continue
            oid = getattr(t.schedule[w - 1], "team_id", None)
            if oid is None or oid not in by_id or oid <= t.team_id:
                continue  # a bye, or the other side already added this game
            out[w].append({"home": t.team_id, "away": oid,
                           "home_score": round(float(t.scores[w - 1] or 0), 2),
                           "away_score": round(float(by_id[oid].scores[w - 1] or 0), 2)})
    return out


def _standings(lg, matchups: dict[int, list[dict]]) -> list[dict]:
    """Team rows, like league/report.py's (minus the box-score extras), plus all-play."""
    allplay = {t.team_id: [0, 0] for t in lg.teams}
    for games in matchups.values():
        scores = {g[side]: g[f"{side}_score"] for g in games for side in ("home", "away")}
        for tid, s in scores.items():
            allplay[tid][0] += sum(1 for o, x in scores.items() if o != tid and x < s)
            allplay[tid][1] += sum(1 for o, x in scores.items() if o != tid and x > s)
    rows = []
    for t in lg.teams:
        owner = (t.owners or [{}])[0]
        rows.append({
            "id": t.team_id, "name": (t.team_name or "").strip() or f"Team {t.team_id}",
            "abbrev": t.team_abbrev,
            "manager": owner.get("firstName") or owner.get("displayName") or "",
            "logo": getattr(t, "logo_url", None) or None,
            "wins": t.wins, "losses": t.losses, "ties": t.ties,
            "points_for": round(t.points_for, 2), "points_against": round(t.points_against, 2),
            "streak": f"{t.streak_type[:1]}{t.streak_length}" if t.streak_length else "",
            "standing": getattr(t, "standing", None),
            "allplay_w": allplay[t.team_id][0], "allplay_l": allplay[t.team_id][1],
        })
    rows.sort(key=lambda r: (r["standing"] or 99, -r["wins"], -r["points_for"]))
    return rows


def build(league_id, season, espn_s2=None, swid=None, relay="/api/espn/") -> str:
    espn_requests.requests = _Http(relay)
    from espn_api.football import League

    lg = League(league_id=int(league_id), year=int(season),
                espn_s2=(espn_s2 or "").strip() or None, swid=_braced(swid))
    current = int(getattr(lg, "current_week", 1) or 1)
    through = max(current - 1, 0)  # current_week is the week in progress; rank finished weeks
    settings = lg.settings
    reg_weeks = int(getattr(settings, "reg_season_count", 0) or 0)
    matchups = _matchups(lg, min(through, reg_weeks) if reg_weeks else through)
    teams = _standings(lg, matchups)
    ctx = SimpleNamespace(through=through, reg_weeks=reg_weeks, matchups=matchups,
                          teams=[{"id": t["id"], "name": t["name"]} for t in teams])
    return json.dumps({
        "league": {"id": int(league_id), "season": int(season),
                   "name": getattr(settings, "name", "") or "Fantasy League",
                   "through_week": through, "current_week": current,
                   "regular_season_weeks": reg_weeks or None},
        "teams": teams,
        "power": power.build(ctx),
    })
