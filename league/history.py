"""League history: every past season's games, keyed by manager so rivalries span years.

ESPN keeps old seasons of a league under the same league id (``League.previousSeasons``).
For each one we load that season's ``League`` and read, per team, ``schedule[i]`` (the
opponent in matchup period ``i + 1``), ``scores[i]`` and ``outcomes[i]`` (``W``/``L``/``T``,
or ``U`` while undecided). Team ids can change from year to year, so teams are matched
across seasons by their primary owner's id.

Output (``window.LEAGUE_DATA.history``)::

    {"seasons": [2025, 2024],
     "games": [{"season", "week", "a", "b", "a_score", "b_score", "playoff"}],  # a, b: manager keys
     "managers": [{"key": owner id, "name": first name, "team": current team id | None}]}

Every game is listed once. Games after the regular season are flagged ``playoff``. Byes,
unplayed games and games the two teams' schedules disagree on are left out rather than guessed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


def _empty() -> dict:
    return {"seasons": [], "games": [], "managers": []}


def owner(team) -> tuple[str, str] | None:
    """``(owner id, first name)`` of a team's primary owner; ``None`` if it has no owner."""
    owners = getattr(team, "owners", None) or []
    first = owners[0] if owners else None
    if not isinstance(first, dict) or not first.get("id"):
        return None
    name = first.get("firstName") or first.get("displayName") or ""
    return str(first["id"]), str(name).strip()


def _score(x) -> float | None:
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return None


def season_games(lg, season: int) -> tuple[list[dict], dict[str, str]]:
    """One past season's played games (each once) plus ``{owner id: first name}``.

    ``lg`` is an espn-api ``League`` after init: ``lg.teams[*].schedule`` holds opponent
    ``Team`` objects. A game is recorded from the lower team id's side, and only when the
    opponent's own schedule agrees it played that team that week.
    """
    reg = int(getattr(getattr(lg, "settings", None), "reg_season_count", 0) or 0)
    owners = {t.team_id: owner(t) for t in lg.teams}
    names = dict(o for o in owners.values() if o)
    games: list[dict] = []
    for team in lg.teams:
        me = owners.get(team.team_id)
        if me is None:
            continue
        outcomes = list(getattr(team, "outcomes", None) or [])
        scores = list(getattr(team, "scores", None) or [])
        for i, opp in enumerate(getattr(team, "schedule", None) or []):
            opp_id = getattr(opp, "team_id", None)
            them = owners.get(opp_id)
            if opp_id is None or opp_id <= team.team_id or them is None:
                continue  # a bye (self), a stray id, or the other side records this game
            if i >= len(outcomes) or outcomes[i] not in ("W", "L", "T"):
                continue  # not played yet
            their_sched = list(getattr(opp, "schedule", None) or [])
            their_scores = list(getattr(opp, "scores", None) or [])
            if i >= len(their_sched) or getattr(their_sched[i], "team_id", None) != team.team_id:
                continue  # the two schedules disagree about this week
            a_score = _score(scores[i] if i < len(scores) else None)
            b_score = _score(their_scores[i] if i < len(their_scores) else None)
            if a_score is None or b_score is None:
                continue
            games.append({"season": season, "week": i + 1, "a": me[0], "b": them[0],
                          "a_score": a_score, "b_score": b_score,
                          "playoff": bool(reg) and i + 1 > reg})
    games.sort(key=lambda g: (g["week"], g["a"], g["b"]))
    return games, names


def _load_season(client, year: int):
    """The espn-api ``League`` for a past season (network)."""
    from espn_api.football import League

    return League(league_id=client.league_id, year=year, espn_s2=client.espn_s2, swid=client.swid)


def build(ctx, load: Callable[[int], Any] | None = None) -> dict:
    """Every past season's games, matched to this season's managers. Empty (and no network
    requests) while ESPN has no previous seasons; a season that fails to load is skipped."""
    lg = ctx.lg
    previous = sorted({int(y) for y in (getattr(lg, "previousSeasons", None) or [])})
    if not previous:
        return _empty()
    load = load or (lambda year: _load_season(ctx.client, year))

    now: dict[str, tuple[int, str]] = {}  # owner id → (current team id, first name)
    for t in lg.teams:
        o = owner(t)
        if o:
            now[o[0]] = (int(t.team_id), o[1])

    seasons: list[int] = []
    games: list[dict] = []
    names: dict[str, str] = {}
    for year in previous:
        try:
            g, n = season_games(load(year), year)
        except Exception as e:  # noqa: BLE001
            log.warning("history: season %s failed to load (%s: %s); skipping.", year, type(e).__name__, e)
            continue
        seasons.append(year)
        games += g
        names.update({k: v for k, v in n.items() if v})  # later seasons win
    games.sort(key=lambda g: (g["season"], g["week"], g["a"], g["b"]))

    keys = sorted({k for g in games for k in (g["a"], g["b"])})
    managers = [{"key": k, "name": now[k][1] if k in now and now[k][1] else names.get(k, ""),
                 "team": now[k][0] if k in now else None} for k in keys]
    return {"seasons": seasons, "games": games, "managers": managers}
