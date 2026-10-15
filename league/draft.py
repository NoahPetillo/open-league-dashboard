"""Draft report card: every pick graded on points scored against where it was taken.
Output: ``window.LEAGUE_DATA.draft``.

How a pick is graded
    ``points`` is his league-scored points over the completed weeks, wherever he played
    (any roster, or free agency). Only QBs, RBs, WRs and TEs ("skill" picks) are graded:
    kickers, head coaches and defensive players are listed with their points, but their
    ``value`` is None because they score on a different scale.

    Among skill picks, ``order`` is the order he was taken (1 = the first skill player
    off the board) and ``points_rank`` is his rank by points (1 = most). Players tied on
    points share the best rank of the tie (1, 2, 2, 4), so a late pick who has scored
    nothing can still land slightly above 0. ``value = order - points_rank``: positive
    means he finished above his draft slot (a steal), negative below it (a bust).

What happened to him since
    ``status`` is "kept" while he's on the drafting team's current roster. Otherwise it
    comes from the drafting team's LAST drop ("dropped") or trade away ("traded") of him in
    ESPN's activity feed. If he's off the roster and the feed has neither ("gone"), ESPN
    didn't log how he left, so nothing is guessed. ``now_team`` is the team whose roster
    holds him now (None: free agent).

    ``let_go_week`` is when the drafting team FIRST let him go (even if it later got him
    back): the first completed week whose last kickoff is after the move. A move in the
    preseason or between weeks lands in the week about to be played. It is None when he
    was never let go, or the move came after the last completed week's last kickoff.

Team grades
    A team's ``value_avg`` is the mean value of its graded picks. Teams are ranked by it
    and graded on a curve: the best gets A+ and the worst F, with the 12-step scale spread
    evenly in between (it fits 12 teams one letter each). Teams with the same average share
    the better rank and grade.
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from typing import Any

SKILL = {"QB", "RB", "WR", "TE"}
SCALE = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F"]
LET_GO = {"DROPPED": "dropped", "TRADE_SENT": "traded"}


# ── inputs ─────────────────────────────────────────────────────────────────────
def _points(ctx, pid: str) -> float:
    """Season to date, wherever he played. Rounded so equal scores compare equal."""
    return round(sum(ctx.pts.get(w, {}).get(pid, 0.0) for w in ctx.weeks), 2)


def _rosters(ctx) -> dict[int, set[str]]:
    """Team id → player ids on its roster right now."""
    out: dict[int, set[str]] = {}
    for t in getattr(ctx.lg, "teams", None) or []:
        tid = getattr(t, "team_id", None)
        if tid is not None:
            out[int(tid)] = {str(p.playerId) for p in getattr(t, "roster", None) or []}
    return out


def _let_goes(activity: list[dict]) -> dict[tuple[int, str], list[tuple[int, str]]]:
    """(team, player) → every time that team dropped or traded him away, oldest first."""
    out: dict[tuple[int, str], list[tuple[int, str]]] = defaultdict(list)
    for act in sorted(activity, key=lambda a: a.get("date", 0)):
        for tid, kind, pid, _amount in act["moves"]:
            if tid is not None and kind in LET_GO:
                out[(int(tid), str(pid))].append((int(act["date"]), kind))
    return out


def _week_of(ctx, date: int) -> int | None:
    """First completed week whose last kickoff is after ``date`` (None: after them all)."""
    for w in sorted(ctx.weeks):
        kick = ctx.kicks.get(w)
        if kick and kick[1] > date:
            return w
    return None


# ── grading ────────────────────────────────────────────────────────────────────
def _grade_picks(picks: list[dict]) -> None:
    """Fill ``order``, ``points_rank`` and ``value`` for skill picks (None for the rest)."""
    graded = [p for p in picks if p["skill"]]  # already in pick order
    first_at: dict[float, int] = {}
    for i, pts in enumerate(sorted((p["points"] for p in graded), reverse=True), 1):
        first_at.setdefault(pts, i)  # ties share the best rank
    for i, p in enumerate(graded, 1):
        p["order"], p["points_rank"] = i, first_at[p["points"]]
        p["value"] = p["order"] - p["points_rank"]
    for p in picks:
        if not p["skill"]:
            p["order"] = p["points_rank"] = p["value"] = None


def _track(ctx, picks: list[dict]) -> None:
    """Fill ``status``, ``now_team`` and ``let_go_week`` (all None without roster data)."""
    owner = {pid: tid for tid, ids in _rosters(ctx).items() for pid in ids}
    lets = _let_goes(ctx.activity)
    for p in picks:
        moves = lets.get((p["team"], p["id"]), [])
        p["let_go_week"] = _week_of(ctx, moves[0][0]) if moves else None
        p["now_team"] = owner.get(p["id"])
        if not owner:
            p["status"] = None
        elif p["now_team"] == p["team"]:
            p["status"] = "kept"
        elif moves:
            p["status"] = LET_GO[moves[-1][1]]  # the move that took him off the roster
        else:
            p["status"] = "gone"


def _curve(rows: list[dict], key: dict[int, Fraction]) -> None:
    """Rank teams by ``key`` (best first) and hand out ``grade`` on the curve."""
    n = len(key)
    for r in rows:
        if r["team"] not in key:
            r["rank"] = r["grade"] = None
            continue
        r["rank"] = 1 + sum(1 for v in key.values() if v > key[r["team"]])
        top = len(SCALE) - 1
        i = ((r["rank"] - 1) * 2 * top + (n - 1)) // (2 * (n - 1)) if n > 1 else 0
        r["grade"] = SCALE[i]


def _best(picks: list[dict]) -> dict | None:
    return max(picks, key=lambda p: (p["value"], p["points"]), default=None)


def _worst(picks: list[dict]) -> dict | None:
    return min(picks, key=lambda p: (p["value"], p["points"]), default=None)


def _team_rows(picks: list[dict], tracked: bool) -> list[dict]:
    rows, key = [], {}
    for tid in sorted({p["team"] for p in picks}):
        mine = [p for p in picks if p["team"] == tid]
        graded = [p for p in mine if p["skill"]]
        kept = [p for p in mine if p["status"] == "kept"]
        best, worst = _best(graded), _worst(graded)
        if graded:
            key[tid] = Fraction(sum(p["value"] for p in graded), len(graded))
        rows.append({
            "team": tid, "graded": len(graded),
            "value_avg": round(float(key[tid]), 2) if tid in key else None,
            "points": round(sum(p["points"] for p in mine), 2),
            "kept": len(kept) if tracked else None,
            "kept_points": round(sum(p["points"] for p in kept), 2) if tracked else None,
            "best_pick": best["pick"] if best else None, "worst_pick": worst["pick"] if worst else None,
        })
    _curve(rows, key)
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["team"]))
    return rows


def _highlights(picks: list[dict], teams: list[dict]) -> dict[str, Any]:
    graded = [p for p in picks if p["skill"]]
    first = [p for p in picks if p["round"] == 1]
    cut = [p for p in picks if p["status"] == "dropped"]
    steal, bust = _best(graded), _worst(graded)
    worst_first = min(first, key=lambda p: (p["points"], p["pick"]), default=None)
    best_first = max(first, key=lambda p: (p["points"], -p["pick"]), default=None)
    earliest = min(cut, key=lambda p: p["pick"], default=None)
    holders = [t for t in teams if t["kept"] is not None]
    most = max(holders, key=lambda t: (t["kept"], t["kept_points"], -t["team"]), default=None)
    return {
        "steal": steal["pick"] if steal else None, "bust": bust["pick"] if bust else None,
        "worst_first_rounder": worst_first["pick"] if worst_first else None,
        "best_first_rounder": best_first["pick"] if best_first else None,
        "earliest_cut": earliest["pick"] if earliest else None,
        "kept_most": most["team"] if most else None,
    }


def build(ctx) -> dict | None:
    draft = sorted(ctx.draft or [], key=lambda p: p["pick"])
    if not draft:
        return None
    picks = []
    for d in draft:
        pid = str(d["id"])
        pos = ctx.pos.get(pid) or "?"
        picks.append({
            "pick": d["pick"], "round": d["round"], "round_pick": d["round_pick"], "team": d["team"],
            "id": pid, "name": d.get("name") or ctx.names.get(pid) or f"Player {pid}",
            "pos": pos, "pro_team": ctx.pro.get(pid, ""),
            "points": _points(ctx, pid), "skill": pos in SKILL,
        })
    _grade_picks(picks)
    _track(ctx, picks)
    tracked = any(p["status"] is not None for p in picks)
    teams = _team_rows(picks, tracked)
    return {
        "through": ctx.through, "rounds": max(p["round"] for p in picks), "teams_n": len(teams),
        "picks": [{k: p[k] for k in ("pick", "round", "round_pick", "team", "id", "name", "pos",
                                     "pro_team", "points", "skill", "order", "points_rank", "value",
                                     "status", "now_team", "let_go_week")} for p in picks],
        "teams": teams,
        "highlights": _highlights(picks, teams),
    }
