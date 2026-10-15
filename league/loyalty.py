"""Player loyalty: players who've never left the roster that drafted them, and the roster
spots with the most turnover. Output: ``window.LEAGUE_DATA.loyalty``.

``build(ctx)`` returns ``{"teams", "revolving_doors", "ride_or_die"}``, or None when there is no
draft to compare against (or no current rosters to tell who is still where).

Per team (``teams``), from the draft and ESPN's transaction log:

* ``drafted`` is the team's number of draft picks; ``kept`` how many of those picks are on its
  roster today, whatever happened in between (dropped and re-added, traded away and back).
* ``day_ones`` ("ride or die") are the picks that never moved at all: no add, drop or trade of
  that player by any team anywhere in the log, and he is on the team's roster today. Each carries
  his season points (the sum of his league points over every completed week, bench weeks included).
* ``distinct`` is how many different players the team has ever had: its draft picks plus everyone
  it got from FA ADDED, WAIVER ADDED or TRADE_RECEIVED, each counted once. ``by_pos`` splits that
  by position.

``revolving_doors`` are the six team and position pairs with the most distinct players
(any position, ties go to the pair with fewer draft picks, i.e. more churn), each with the
player names in the order they arrived (draft first, then by date) and how many of them were
drafted. ``ride_or_die`` is the ten best day-ones in the league by season points.
"""

from __future__ import annotations

from collections import defaultdict

ACQUIRED = {"FA ADDED", "WAIVER ADDED", "TRADE_RECEIVED"}
LET_GO = {"DROPPED", "TRADE_SENT"}
DOORS = 6
RIDERS = 10


def _current(ctx) -> dict[int, set[str]]:
    """Team id → ids of the players on its roster right now."""
    out: dict[int, set[str]] = {}
    for team in getattr(getattr(ctx, "lg", None), "teams", None) or []:
        out[int(team.team_id)] = {str(p.playerId) for p in getattr(team, "roster", None) or []}
    return out


def _arrivals(ctx) -> dict[int, list[str]]:
    """Team id → every player it has had, in the order he first arrived: its draft picks, then
    each add or trade-in by date. A player who comes back is not counted twice."""
    out: dict[int, list[str]] = defaultdict(list)
    seen: dict[int, set[str]] = defaultdict(set)

    def arrive(team: int, pid: str) -> None:
        if pid and pid not in seen[team]:
            seen[team].add(pid)
            out[team].append(pid)

    for pick in sorted(ctx.draft, key=lambda p: p["pick"]):
        arrive(int(pick["team"]), str(pick["id"]))
    for act in sorted(ctx.activity, key=lambda a: a.get("date", 0)):
        for tid, kind, pid, _amount in act["moves"]:
            if tid is not None and kind in ACQUIRED:
                arrive(int(tid), str(pid))
    return out


def _season_points(ctx, pid: str) -> float:
    return round(sum(ctx.pts.get(w, {}).get(pid, 0.0) for w in ctx.weeks), 2)


def build(ctx) -> dict | None:
    if not ctx.draft:
        return None
    current = _current(ctx)
    if not any(current.values()):
        return None
    moved = {str(pid) for act in ctx.activity for _t, kind, pid, _a in act["moves"]
             if pid and kind in ACQUIRED | LET_GO}
    arrivals = _arrivals(ctx)
    picks: dict[int, list[str]] = defaultdict(list)
    for pick in sorted(ctx.draft, key=lambda p: p["pick"]):
        picks[int(pick["team"])].append(str(pick["id"]))

    def name(pid: str) -> str:
        return ctx.names.get(pid) or f"Player {pid}"

    teams, riders, pairs = [], [], defaultdict(list)
    for tid in sorted({int(t["id"]) for t in getattr(ctx, "teams", None) or []} | set(picks) | set(arrivals)):
        mine = current.get(tid, set())
        day_ones = [{"id": pid, "name": name(pid), "pos": ctx.pos.get(pid, "?"), "points": _season_points(ctx, pid)}
                    for pid in picks[tid] if pid not in moved and pid in mine]
        day_ones.sort(key=lambda p: -p["points"])
        by_pos: dict[str, int] = defaultdict(int)
        for pid in arrivals[tid]:
            by_pos[ctx.pos.get(pid, "?")] += 1
            pairs[(tid, ctx.pos.get(pid, "?"))].append(pid)
        teams.append({"team": tid, "drafted": len(picks[tid]), "kept": sum(1 for pid in picks[tid] if pid in mine),
                      "day_ones": day_ones, "distinct": len(arrivals[tid]),
                      "by_pos": dict(sorted(by_pos.items(), key=lambda kv: (-kv[1], kv[0])))})
        riders += [{"team": tid, **p} for p in day_ones]

    riders.sort(key=lambda p: (-p["points"], p["team"], p["id"]))
    drafted_by = {tid: set(ids) for tid, ids in picks.items()}

    def door(tid: int, pos: str, ids: list[str]) -> dict:
        return {"team": tid, "pos": pos, "count": len(ids), "drafted": sum(1 for p in ids if p in drafted_by.get(tid, ())),
                "players": [name(p) for p in ids]}

    doors = sorted((door(tid, pos, ids) for (tid, pos), ids in pairs.items()),
                   key=lambda d: (-d["count"], d["drafted"], d["team"], d["pos"]))
    return {"teams": teams, "revolving_doors": doors[:DOORS], "ride_or_die": riders[:RIDERS]}
