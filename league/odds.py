"""Season odds: the last-place race (who does the punishment) and playoff odds,
now and as they stood after every completed week.

``build(ctx)`` returns ``{"punishment": ..., "history": ...}``:
    punishment — ``punishment.simulate`` for the unplayed regular-season weeks, with
                 playoff odds (None once the regular season is over).
    history    — the odds as they stood after each completed regular-season week
                 (week 0 = preseason): {"weeks": [0, 1, ...], "teams": [{"team": id,
                 "p_playoffs": [...], "p_last": [...], "p_division": [...]}]}.
                 Each past week re-simulates the rest of the season from that week's
                 standings, using only the scores known by then. The last point is
                 the live result, so the chart ends on the numbers the page shows.
"""

from __future__ import annotations

from league.punishment import DEFAULT_SIMS, simulate

MAIN_SIMS = DEFAULT_SIMS
HISTORY_SIMS = 5000  # past weeks only need to be smooth enough for a line chart


def _standings(team_ids: list[int], matchups: dict[int, list[dict]],
               divisions: dict[int, int], through: int) -> list[dict]:
    """Every team's state after week ``through``, from the box-score matchups:
    record (equal scores = a tie), points for, division wins and weekly scores."""
    st = {t: {"id": t, "wins": 0, "losses": 0, "ties": 0, "points_for": 0.0,
              "div_wins": 0.0, "scores": []} for t in team_ids}
    for week in sorted(w for w in matchups if w <= through):
        for g in matchups[week]:
            a, b, sa, sb = g["home"], g["away"], g["home_score"], g["away_score"]
            if a not in st or b not in st:
                continue
            division_game = a in divisions and divisions.get(a) == divisions.get(b)
            for me, mine, theirs in ((a, sa, sb), (b, sb, sa)):
                s = st[me]
                s["points_for"] += mine
                s["scores"].append(mine)
                key = "wins" if mine > theirs else "losses" if mine < theirs else "ties"
                s[key] += 1
                if division_game:
                    s["div_wins"] += 1 if mine > theirs else 0.5 if mine == theirs else 0
    return [st[t] for t in team_ids]


def _run(ctx, through: int, sims: int) -> dict:
    """Simulate the regular season from the standings after week ``through``."""
    weeks_left = list(range(through + 1, ctx.reg_weeks + 1))
    ids = [t["id"] for t in ctx.teams]
    schedule = {w: g for w, g in ctx.schedule.items() if w in weeks_left}
    return simulate(_standings(ids, ctx.matchups, ctx.divisions, through), schedule, weeks_left,
                    sims=sims, playoff_teams=ctx.playoff_teams, divisions=ctx.divisions)


def _history(ctx, through: int, live: dict | None) -> dict:
    """Odds after each week 0..``through``; ``live`` is the already-run result for the
    last of them (reused so the final point matches the page exactly)."""
    weeks = list(range(through + 1))
    results = [live if k == through and live is not None else _run(ctx, k, HISTORY_SIMS)
               for k in weeks]
    series = []
    for t in ctx.teams:
        rows = [next(x for x in r["teams"] if x["id"] == t["id"]) for r in results]
        series.append({"team": t["id"],
                       "p_playoffs": [x.get("p_playoffs") for x in rows],
                       "p_last": [x["p_last"] for x in rows],
                       "p_division": [x.get("p_division") for x in rows]})
    return {"weeks": weeks, "teams": series}


def build(ctx) -> dict:
    if not ctx.reg_weeks:
        return {"punishment": None, "history": None}
    through = min(ctx.through, ctx.reg_weeks)  # playoff weeks don't count toward the standings
    season_over = through >= ctx.reg_weeks
    live = None if season_over else _run(ctx, through, MAIN_SIMS)
    return {"punishment": live, "history": _history(ctx, through, live)}
