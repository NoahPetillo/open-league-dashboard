"""Waiver drop regret: players a team dropped who kept scoring after they left.
Output: ``window.LEAGUE_DATA.drops``.

``build(ctx)`` returns ``{"through", "drops", "teams"}`` (or None when nobody has dropped a
quarterback, running back, wide receiver or tight end). Kickers, head coaches and defensive
players are left out: everyone streams them.

The regret window — every DROPPED move in the activity feed opens one. It closes when the
same team gets that player back (FA ADDED, WAIVER ADDED or TRADE_RECEIVED by that team after
the drop), and stays open otherwise. If a team drops the same player twice, that is two entries.

A completed week counts for a drop when the player's game kicked off after the drop and before
the window closed. His kickoff is ``ctx.kickoff[week][player]``. ESPN only has one while he is on
a fantasy roster, so a free agent's game start is read off a teammate instead: any player of his
NFL team on a fantasy roster that week has the same kickoff. With no teammate to read it from (a bye
week, or nobody from that team rostered) the week's first kickoff stands in, so a drop made once
the week's games have started never claims such a week.

For each counted week the drop keeps his exact league points, ``holder`` (the team whose box-score
roster had him that week, or None for a free agent) and ``started`` (he was in that team's
starting lineup). A team that picked him up only after his game kicked off (``ctx.late``) was not
his holder: he was a free agent when he scored. ``points_since`` and ``weeks_since`` add up the
counted weeks.
``for_others`` is the part that went to a different fantasy team than the one that dropped him:
``points`` while on that other team's roster, ``started_points`` while in its starting lineup.
A week he spent back on the dropping team's own box-score roster is not "for others".

Drops made after the last completed week have ``weeks_since`` 0. They stay in the data, so the
page can say nothing about them until a week finishes.
"""

from __future__ import annotations

from collections import defaultdict

SKILL = {"QB", "RB", "WR", "TE"}
ACQUIRED = {"FA ADDED", "WAIVER ADDED", "TRADE_RECEIVED"}
NO_TEAM = {"", "None", "FA"}  # what ESPN calls the NFL team of a player who has none


def _events(activity: list[dict]) -> list[tuple[int, int, str, str]]:
    """``(date, team, kind, player id)`` for every move that has both a team and a player,
    oldest first (feed order breaks ties)."""
    out = []
    for act in sorted(activity, key=lambda a: a.get("date", 0)):
        for tid, kind, pid, _amount in act["moves"]:
            if tid is None or not pid:
                continue
            out.append((int(act["date"]), int(tid), kind, str(pid)))
    return out


def _windows(events: list[tuple[int, int, str, str]], pos: dict[str, str]) -> list[dict]:
    """One regret window per skill-position drop: ``{team, id, date, end}``, where ``end`` is
    the date the same team got him back (None while he is still gone)."""
    later: dict[tuple[int, str], list[tuple[int, int, str]]] = defaultdict(list)
    for i, (date, team, kind, pid) in enumerate(events):
        if kind in ACQUIRED:
            later[(team, pid)].append((i, date, kind))
    out = []
    for i, (date, team, kind, pid) in enumerate(events):
        if kind != "DROPPED" or pos.get(pid) not in SKILL:
            continue
        back = next((d for j, d, _k in later[(team, pid)] if j > i), None)
        out.append({"team": team, "id": pid, "date": date, "end": back})
    return out


def _team_kickoffs(ctx) -> dict[tuple[int, str], int | None]:
    """``(week, NFL team)`` → when that team's game kicked off, read off its players who sat on a
    fantasy roster that week (None if they disagree, e.g. a player who changed teams)."""
    seen: dict[tuple[int, str], set[int]] = defaultdict(set)
    for w, by_player in (getattr(ctx, "kickoff", None) or {}).items():
        for pid, k in by_player.items():
            team = ctx.pro.get(pid)
            if team and team not in NO_TEAM:
                seen[(w, team)].add(k)
    return {key: next(iter(ks)) if len(ks) == 1 else None for key, ks in seen.items()}


def _counted_weeks(ctx, team_kicks: dict, pid: str, date: int, end: int | None) -> list[int]:
    """Completed weeks whose game for ``pid`` kicked off inside the window (date, end)."""
    kickoff = getattr(ctx, "kickoff", None) or {}
    out = []
    for w in ctx.weeks:
        k = kickoff.get(w, {}).get(pid)          # his own, while on a fantasy roster
        if k is None:
            k = team_kicks.get((w, ctx.pro.get(pid)))  # a free agent: his NFL team's game
        if k is None:
            span = ctx.kicks.get(w)               # a bye, or no teammate rostered: the week's first kickoff
            k = span[0] if span else None
        if k is not None and k > date and (end is None or k < end):
            out.append(w)
    return out


def _current_owner(ctx) -> dict[str, int]:
    """Player id → the team whose roster has him right now."""
    out: dict[str, int] = {}
    for team in getattr(getattr(ctx, "lg", None), "teams", None) or []:
        for p in getattr(team, "roster", None) or []:
            out[str(p.playerId)] = int(team.team_id)
    return out


def build(ctx) -> dict | None:
    windows = _windows(_events(ctx.activity), ctx.pos)
    if not windows:
        return None
    holder = {w: {pid: tid for tid, r in ctx.rosters.get(w, {}).items() for pid in r.players}
              for w in ctx.weeks}
    late = getattr(ctx, "late", None) or {}
    team_kicks = _team_kickoffs(ctx)
    owner = _current_owner(ctx)
    drops = []
    for win in windows:
        pid, team = win["id"], win["team"]
        weeks = []
        for w in _counted_weeks(ctx, team_kicks, pid, win["date"], win["end"]):
            on = holder[w].get(pid)
            if on is not None and pid in late.get(w, {}).get(on, ()):
                on = None  # that team picked him up after his game: he was a free agent when he scored
            lineup = ctx.rosters[w][on].started if on is not None else set()
            weeks.append({"week": w, "points": round(ctx.pts.get(w, {}).get(pid, 0.0), 2),
                          "holder": on, "started": pid in lineup})
        away = [x for x in weeks if x["holder"] not in (None, team)]
        nfl = ctx.pro.get(pid, "")
        drops.append({
            "team": team, "id": pid, "name": ctx.names.get(pid) or f"Player {pid}",
            "pos": ctx.pos.get(pid, "?"), "pro_team": "" if nfl in NO_TEAM else nfl, "date": win["date"],
            "points_since": round(sum(x["points"] for x in weeks), 2), "weeks_since": len(weeks),
            "for_others": {"points": round(sum(x["points"] for x in away), 2),
                           "started_points": round(sum(x["points"] for x in away if x["started"]), 2)},
            "now_team": owner.get(pid), "readded": win["end"] is not None, "weeks": weeks,
        })
    drops.sort(key=lambda d: (-d["points_since"], d["date"], d["team"], d["id"]))
    regret: dict[int, float] = defaultdict(float)
    count: dict[int, int] = defaultdict(int)
    for d in drops:
        regret[d["team"]] += d["points_since"]
        count[d["team"]] += 1
    teams = sorted({int(t["id"]) for t in getattr(ctx, "teams", None) or []} | set(count))
    return {"through": ctx.through, "drops": drops,
            "teams": [{"team": t, "drops": count[t], "regret_points": round(regret[t], 2)} for t in teams]}
