"""Live lineups for the current week — small and cheap, meant to refresh every ~15 min.

One ESPN read (this week's box scores) gives every team's lineup with live points,
ESPN projections and game state. Kept separate from ``report.build_report`` (which
walks the whole season) so frequent refreshes stay fast.

ESPN gives no live game clock (espn-api's ``game_played`` only flips to 100 three
hours after kickoff), so status comes from kickoff time: "live" = kicked off within
the last ~3.5 hours. espn-api builds kickoff as a naive LOCAL datetime.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from league.espn import EspnClient

log = logging.getLogger(__name__)

NON_STARTING = {"BE", "IR"}
GAME_LENGTH = timedelta(hours=3, minutes=30)
# Display order of starting slots; anything else sorts after these.
SLOT_ORDER = ["QB", "RB", "WR", "TE", "RB/WR/TE", "OP", "DP", "K", "D/ST", "HC", "P"]


def _status(bp, now: datetime) -> str:
    if getattr(bp, "on_bye_week", False):
        return "bye"
    kickoff = getattr(bp, "game_date", None)
    if kickoff is None:
        return "final" if getattr(bp, "game_played", 0) else "upcoming"
    if now < kickoff:
        return "upcoming"
    return "live" if now < kickoff + GAME_LENGTH else "final"


def _player(bp, now: datetime) -> dict:
    kickoff = getattr(bp, "game_date", None)
    injury = getattr(bp, "injuryStatus", None)
    return {
        "id": str(bp.playerId), "name": bp.name, "pos": bp.position,
        "slot": bp.slot_position, "team": getattr(bp, "proTeam", None),
        "points": round(float(bp.points or 0), 2),
        "projected": round(float(getattr(bp, "projected_points", 0) or 0), 2),
        "status": _status(bp, now),
        "kickoff": kickoff.astimezone().isoformat() if kickoff else None,
        "injury": injury if injury and injury not in ("ACTIVE", "NORMAL") else None,
    }


def _side(team, score, projected, lineup, now) -> dict:
    players = [_player(bp, now) for bp in lineup or []]
    starters = [p for p in players if p["slot"] not in NON_STARTING]
    order = {s: i for i, s in enumerate(SLOT_ORDER)}
    starters.sort(key=lambda p: (order.get(p["slot"], len(order)), -p["projected"]))
    bench = sorted((p for p in players if p["slot"] in NON_STARTING),
                   key=lambda p: (p["slot"] == "IR", -p["points"], -p["projected"]))
    return {
        "team": team.team_id, "score": round(float(score or 0), 2),
        "projected": round(float(projected or 0), 2),
        "yet_to_play": sum(1 for p in starters if p["status"] == "upcoming"),
        "playing": sum(1 for p in starters if p["status"] == "live"),
        "starters": starters, "bench": bench,
    }


def build_live(client: EspnClient, week: int | None = None) -> dict:
    lg = client.league()
    week = week or int(getattr(lg, "current_week", 1) or 1)
    now = datetime.now()  # naive local, to match espn-api's kickoff times
    matchups = []
    for m in lg.box_scores(week):
        if getattr(m.home_team, "team_id", None) is None or getattr(m.away_team, "team_id", None) is None:
            continue
        matchups.append({
            "home": _side(m.home_team, m.home_score, m.home_projected, m.home_lineup, now),
            "away": _side(m.away_team, m.away_score, m.away_projected, m.away_lineup, now),
        })
    out = {"week": week, "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
           "matchups": matchups}
    try:  # pregame odds + this week's swings so far; never worth losing the lineups over
        from league import winprob
        out["winprob"] = winprob.live(out)
    except Exception as e:  # noqa: BLE001
        log.warning("win probability failed (%s: %s); leaving it out.", type(e).__name__, e)
        out["winprob"] = None
    return out
