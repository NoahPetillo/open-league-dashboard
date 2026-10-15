"""FAAB report card: what every waiver / free-agent pickup produced, and the FAAB
dollars that changed hands in trades.

``build(ctx)`` returns ``{"budget", "teams", "faab_trades", "highlights"}`` (or None for
a league without a FAAB budget).

How a pickup is credited — a "stint" runs from the add until the same team lets the
player go (its next drop, trade away, or re-add of him). A completed week counts for
the stint when the add happened before that week's last kickoff, the stint hadn't ended
before the week's first kickoff, and the player is on that team's box-score roster that
week. ``points`` sums his league points over those weeks, ``started_points`` only the
weeks he was in the starting lineup. A week claimed by two stints of the same player on
the same team (dropped and re-added in the same week) goes to the later add.

"FAAB left" is ESPN's own number (budget minus its ``acquisitionBudgetSpent`` counter),
falling back to budget − bids − FAAB traded away + FAAB received when ESPN's counter is
missing. Whatever ESPN's number has that bids and trades don't explain is ``commish``:
FAAB the commissioner added or took away by hand (ESPN doesn't log those; this league's
commish has handed out $1 rewards). So for every team:
    left = budget − spent_on_bids − faab_out + faab_in + commish
"""

from __future__ import annotations

from statistics import median
from typing import Any

PICKUPS = {"WAIVER ADDED": "waiver", "FA ADDED": "free agent"}
LET_GO = {"DROPPED", "TRADE_SENT"}


# ── events ─────────────────────────────────────────────────────────────────────
def _flatten(activity: list[dict]) -> list[tuple[int, int, str, str, int]]:
    """``(date, team, kind, player id, amount)`` for every move, oldest first (feed order
    breaks ties). Moves with no team are dropped."""
    out = []
    for act in sorted(activity, key=lambda a: a.get("date", 0)):
        for tid, kind, pid, amount in act["moves"]:
            if tid is None:
                continue
            out.append((int(act["date"]), int(tid), kind, str(pid), int(amount or 0)))
    return out


def _stints(events: list[tuple[int, int, str, str, int]]) -> list[dict]:
    """One record per pickup: who, when, how much, and when that team let him go
    (``end``, None while he's still held)."""
    by_player: dict[tuple[int, str], list[int]] = {}
    for i, (_d, team, kind, pid, _a) in enumerate(events):
        if kind in LET_GO or kind in PICKUPS:
            by_player.setdefault((team, pid), []).append(i)
    out = []
    for i, (date, team, kind, pid, amount) in enumerate(events):
        if kind not in PICKUPS:
            continue
        later = [j for j in by_player[(team, pid)] if j > i]
        out.append({"seq": i, "date": date, "team": team, "id": pid, "bid": amount,
                    "kind": PICKUPS[kind], "end": events[later[0]][0] if later else None})
    return out


def _weeks_held(stint: dict, weeks: list[int], rosters, kicks) -> list[int]:
    """Completed weeks this stint covers (see the module docstring)."""
    out = []
    for w in weeks:
        roster = rosters.get(w, {}).get(stint["team"])
        if roster is None or stint["id"] not in roster.players:
            continue
        first_last = kicks.get(w)
        if first_last:
            first, last = first_last
            if stint["date"] >= last:
                continue
            if stint["end"] is not None and stint["end"] < first:
                continue
        out.append(w)
    return out


def _pickups(ctx) -> list[dict]:
    """Every pickup with its production, oldest first."""
    stints = _stints(_flatten(ctx.activity))
    claimed: set[tuple[int, str, int]] = set()
    held: dict[int, list[int]] = {}
    for s in sorted(stints, key=lambda s: -s["seq"]):  # later adds claim contested weeks first
        mine = [w for w in _weeks_held(s, ctx.weeks, ctx.rosters, ctx.kicks)
                if (s["team"], s["id"], w) not in claimed]
        claimed.update((s["team"], s["id"], w) for w in mine)
        held[s["seq"]] = mine
    out = []
    for s in stints:
        mine = held[s["seq"]]
        pts = [ctx.pts.get(w, {}).get(s["id"], 0.0) for w in mine]
        starts = [ctx.pts.get(w, {}).get(s["id"], 0.0) for w in mine
                  if s["id"] in ctx.rosters[w][s["team"]].started]
        out.append({
            "team": s["team"], "id": s["id"], "name": ctx.names.get(s["id"]) or f"Player {s['id']}",
            "pos": ctx.pos.get(s["id"], "?"), "pro_team": ctx.pro.get(s["id"], ""),
            "bid": s["bid"], "kind": s["kind"], "date": s["date"],
            "weeks": len(mine), "points": round(sum(pts), 2), "started_points": round(sum(starts), 2),
            "let_go": s["end"] is not None,  # dropped or traded away since
        })
    return out


# ── FAAB in trades ─────────────────────────────────────────────────────────────
def _transfers(activity: list[dict]) -> list[dict]:
    """FAAB dollars that moved in accepted trades, as ``{date, from, to, amount}``.
    Each FAAB_SENT is paired with the FAAB_RECEIVED of the same amount in the same
    feed entry; anything that can't be paired is left out."""
    out = []
    for act in sorted(activity, key=lambda a: a.get("date", 0)):
        sent = [(int(t), int(a)) for t, k, _p, a in act["moves"] if k == "FAAB_SENT" and t is not None]
        got = [(int(t), int(a)) for t, k, _p, a in act["moves"] if k == "FAAB_RECEIVED" and t is not None]
        used: set[int] = set()
        for frm, amount in sent:
            k = next((i for i, (to, a) in enumerate(got) if i not in used and a == amount and to != frm), None)
            if k is None:
                continue
            used.add(k)
            out.append({"date": int(act["date"]), "from": frm, "to": got[k][0], "amount": amount})
    return out


def _trade_id(trades: list[dict], date: int, a: int, b: int, amount: int) -> int | None:
    """The graded trade that FAAB belonged to: same date, both teams on it — and when
    several trades share a date, the one whose side recorded sending that much."""
    cands = [t for t in trades if t.get("date") == date
             and {a, b} <= {s["team"] for s in t["sides"]}]
    for t in cands:
        side = next(s for s in t["sides"] if s["team"] == a)
        if side.get("faab_sent", 0) >= amount:
            return t["id"]
    return cands[0]["id"] if len(cands) == 1 else None


# ── per-team + league rollups ──────────────────────────────────────────────────
def _num(x: float) -> int | float:
    return int(x) if float(x).is_integer() else round(float(x), 2)


def _left(team: int, budget: int, counters: dict, bids: int, faab_out: int, faab_in: int) -> tuple[int | float, str]:
    """ESPN's own FAAB remaining; our arithmetic when ESPN's counter is missing."""
    spent = (counters.get(team) or {}).get("acquisitionBudgetSpent")
    if isinstance(spent, int | float) and not isinstance(spent, bool):
        return _num(budget - spent), "espn"
    return _num(budget - bids - faab_out + faab_in), "computed"


def _per_dollar(spent: float, started: float) -> float | None:
    return round(spent / started, 2) if spent > 0 and started > 0 else None


def _pts_per_dollar(p: dict) -> float:
    return p["started_points"] / p["bid"]


def _best_pickup(picks: list[dict]) -> dict | None:
    best = max(picks, key=lambda p: (p["started_points"], -p["bid"]), default=None)
    return best if best and best["started_points"] > 0 else None


def _highlights(picks: list[dict]) -> dict[str, Any]:
    """League-wide standouts. A pickup that never made a finished week's roster for the
    team that won him (just claimed, or flipped in a trade) can't be judged and is skipped,
    except for biggest_bid.

    best_value — paid pickup (bid > 0) with the most started points per $.
    best_free — $0 pickup with the most started points.
    bust — of the paid pickups that returned no more than the median started points per $
           (``median_pts_per_dollar``; needs at least two paid pickups), the biggest bid.
           Ties go to the fewest started points, then the most weeks on the roster.
    biggest_bid — the single highest winning bid.
    """
    judged = [p for p in picks if p["weeks"] > 0]
    paid = [p for p in judged if p["bid"] > 0]
    best_value = max((p for p in paid if p["started_points"] > 0),
                     key=lambda p: (_pts_per_dollar(p), p["started_points"]), default=None)
    free = [p for p in judged if p["bid"] == 0 and p["started_points"] > 0]
    best_free = max(free, key=lambda p: p["started_points"], default=None)
    med = median(_pts_per_dollar(p) for p in paid) if len(paid) >= 2 else None
    low = [p for p in paid if p is not best_value and _pts_per_dollar(p) <= med] if med is not None else []
    bust = max(low, key=lambda p: (p["bid"], -p["started_points"], p["weeks"]), default=None)
    bids = [p for p in picks if p["bid"] > 0]
    biggest = max(bids, key=lambda p: (p["bid"], -p["date"]), default=None)
    return {"best_value": best_value, "best_free": best_free, "bust": bust, "biggest_bid": biggest,
            "median_pts_per_dollar": round(med, 2) if med is not None else None}


def build(ctx) -> dict | None:
    budget = int(ctx.faab_budget or 0)
    if not budget:
        return None
    picks = _pickups(ctx)
    transfers = _transfers(ctx.activity)
    out_of: dict[int, int] = {}
    into: dict[int, int] = {}
    for tid, kind, _p, amount in (m for a in ctx.activity for m in a["moves"]):
        if tid is None:
            continue
        if kind == "FAAB_SENT":
            out_of[int(tid)] = out_of.get(int(tid), 0) + int(amount or 0)
        elif kind == "FAAB_RECEIVED":
            into[int(tid)] = into.get(int(tid), 0) + int(amount or 0)

    teams = []
    for t in ctx.teams:
        tid = t["id"]
        mine = [p for p in picks if p["team"] == tid]
        bids = sum(p["bid"] for p in mine)
        started = round(sum(p["started_points"] for p in mine), 2)
        left, source = _left(tid, budget, ctx.counters or {}, bids, out_of.get(tid, 0), into.get(tid, 0))
        commish = _num(left - (budget - bids - out_of.get(tid, 0) + into.get(tid, 0)))
        teams.append({
            "team": tid, "budget": budget, "left": left, "left_source": source,
            "spent_on_bids": bids, "bids_won": sum(1 for p in mine if p["bid"] > 0),
            "pickups": len(mine), "pickup_points": round(sum(p["points"] for p in mine), 2),
            "pickup_started_points": started, "dollars_per_started_point": _per_dollar(bids, started),
            "faab_in": into.get(tid, 0), "faab_out": out_of.get(tid, 0), "commish": commish,
            "best_pickup": _best_pickup(mine),
            "pickup_list": sorted(mine, key=lambda p: -p["date"]),
        })

    faab_trades = [{"trade_id": _trade_id(ctx.trades, x["date"], x["from"], x["to"], x["amount"]), **x}
                   for x in transfers]
    return {"budget": budget, "teams": teams, "faab_trades": faab_trades, "highlights": _highlights(picks)}
