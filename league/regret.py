"""Trade regret meter: what each side's received players have scored since a trade, week
by week, wherever they played. Output: ``window.LEAGUE_DATA.regret``.

The trade ledger (``report.py``) grades what a trade did to starting lineups. This is the
plain "who got more points" argument: for every graded trade, the raw league points of
the players each side received, from the trade onward, even after the player was flipped
to someone else or cut and left sitting in free agency (``ctx.pts`` carries those weeks).

A week counts for a trade from its ``first_week`` through ``ctx.through``. A player's points
in a week count only if his game kicked off after the trade went through:
  * his kickoff that week (``ctx.kickoff``) is after the trade's date, or
  * he has no kickoff entry that week (bye week, or in free agency) and the week's first
    kickoff of the whole league (``ctx.kicks``) is after the trade's date. A bye scores 0
    anyway; a free agent whose game we can't time only counts when every game that week
    came after the trade.
So a trade made Friday gets no credit for a Thursday game. A week that doesn't count for
a player is 0 in his ``weekly`` and listed in his ``skipped`` (the page shows a dash, since
he may well have scored in that game).

``build(ctx)`` returns ``{"trades": [...], "pending": n}``, newest trade first, or None
when no trade has been graded. Each trade::

    {"id", "date", "first_week", "weeks": [week, ...],
     "sides": [{"team", "players": [{"id", "name", "pos", "weekly", "total", "skipped"?}],
                "weekly", "cumulative", "total", "faab_received"}],
     "leader": team id, or None on an exact tie, "margin": leader's total minus the next
     best side's (0 on a tie), "lead_changes": times the running leader changed hands}

Players are sorted by total, best first. ``lead_changes`` compares each week's running
totals and skips weeks where the top spot is tied. A trade also gets ``"gaps": n`` when ESPN
had no points at all for n counted player-weeks (they're counted as 0).
"""

from __future__ import annotations


def _counts(ctx, week: int, pid: str, date: int, first_week: int) -> bool:
    """Does this player's ``week`` count for a trade made at ``date`` (epoch ms)?"""
    kick = ctx.kickoff.get(week, {}).get(pid)
    if kick is not None:
        return kick > date
    span = ctx.kicks.get(week)
    if span is None:  # no kickoff times at all: can't prove the first week, trust later ones
        return week > first_week
    return span[0] > date


def _running(values: list[float]) -> list[float]:
    out, total = [], 0.0
    for v in values:
        total = round(total + v, 2)
        out.append(total)
    return out


def _lead_changes(sides: list[dict], n_weeks: int) -> int:
    """How often the running leader changed hands. Weeks tied at the top are skipped, so
    A, tie, B is one change and A, tie, A is none."""
    last, changes = None, 0
    for i in range(n_weeks):
        cum = [s["cumulative"][i] for s in sides]
        top = max(cum)
        if cum.count(top) > 1:
            continue
        lead = cum.index(top)
        if last is not None and lead != last:
            changes += 1
        last = lead
    return changes


def _side(ctx, side: dict, weeks: list[int], date: int, first_week: int) -> tuple[dict, int]:
    players, gaps = [], 0
    for p in side["received"]:
        pid = str(p["id"])
        row, skipped = [], []
        for w in weeks:
            if not _counts(ctx, w, pid, date, first_week):
                row.append(0.0)
                skipped.append(w)
                continue
            got = ctx.pts.get(w, {})
            if pid not in got:
                gaps += 1
            row.append(round(float(got.get(pid) or 0.0), 2))
        player = {"id": pid, "name": p.get("name") or pid, "pos": p.get("pos") or "?",
                  "weekly": row, "total": round(sum(row), 2)}
        if skipped:
            player["skipped"] = skipped
        players.append(player)
    players.sort(key=lambda p: (-p["total"], p["name"]))
    weekly = [round(sum(p["weekly"][i] for p in players), 2) for i in range(len(weeks))]
    cumulative = _running(weekly)
    return ({"team": side["team"], "players": players, "weekly": weekly, "cumulative": cumulative,
             "total": cumulative[-1] if cumulative else 0.0,
             "faab_received": side.get("faab_received", 0)}, gaps)


def _trade(ctx, trade: dict) -> dict | None:
    first, date = trade["first_week"], trade["date"]
    weeks = list(range(first, ctx.through + 1))
    if not weeks:
        return None
    built = [_side(ctx, s, weeks, date, first) for s in trade["sides"]]
    sides = [s for s, _ in built]
    totals = sorted((s["total"] for s in sides), reverse=True)
    leaders = [s["team"] for s in sides if s["total"] == totals[0]]
    out = {"id": trade["id"], "date": trade["date"], "first_week": first, "weeks": weeks,
           "sides": sides, "leader": leaders[0] if len(leaders) == 1 else None,
           "margin": round(totals[0] - totals[1], 2) if len(totals) > 1 else 0.0,
           "lead_changes": _lead_changes(sides, len(weeks))}
    gaps = sum(g for _, g in built)
    if gaps:
        out["gaps"] = gaps
    return out


def build(ctx) -> dict | None:
    graded = [t for t in ctx.trades if t.get("first_week") is not None]
    rows = [_trade(ctx, t) for t in sorted(graded, key=lambda t: (t["date"], t["id"]), reverse=True)]
    rows = [r for r in rows if r]
    if not rows:
        return None
    return {"trades": rows, "pending": len(ctx.trades) - len(graded)}
