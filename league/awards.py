"""Weekly awards and the season trophy case — everything comes from the box scores.

Every completed week hands out the same ten awards (see ``TITLES``). Team awards
use only teams that actually played a matchup that week (a playoff bye has a
roster but no game, so it can't "win" the toilet bowl with a 0). Player awards
look at who was in the starting lineup (``WeekRoster.started``); anyone else on the
roster counts as bench — the report can't tell the bench from IR.

Ties: values are compared at ESPN's two-decimal precision. If several teams (or
players) share the exact winning value, the award goes to one of them by a fixed
rule (lower team id; for the shame awards on players, the lower-scoring team first)
and ``tied`` says how many others shared it, so the page never claims "only".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

TITLES: dict[str, str] = {
    "top_dog": "Top dog",
    "toilet_bowl": "Toilet bowl",
    "blowout": "Blowout",
    "nail_biter": "Nail-biter",
    "robbed": "Robbed",
    "stole_one": "Stole one",
    "bench_warmer": "Points left on the bench",
    "mvp": "MVP",
    "dud": "Dud",
    "bench_blunder": "Bench blunder",
}

# Kickers, punters, defenses and head coaches score in odd ways (a head coach can
# post -5 on a normal week); a bad day from one isn't a "dud" the way a 0-point
# receiver is.
NO_DUD_POSITIONS = {"K", "P", "D/ST", "DST", "DEF", "HC"}

# (value, tiebreak, item): ``tiebreak`` is compared ascending after the value.
Cand = tuple[float, tuple, Any]


@dataclass(frozen=True)
class Side:
    """One team's side of a played matchup."""
    team: int
    score: float
    opp: int
    opp_score: float


def _sides(games: list[dict]) -> list[Side]:
    """Both sides of every played matchup."""
    out = []
    for g in games:
        h, a = int(g["home"]), int(g["away"])
        hs, as_ = round(float(g["home_score"]), 2), round(float(g["away_score"]), 2)
        out += [Side(h, hs, a, as_), Side(a, as_, h, hs)]
    return out


def _pick(cands: list[Cand], *, high: bool) -> tuple[Cand, int] | None:
    """Best candidate and how many OTHER candidates share its exact value."""
    if not cands:
        return None
    sign = -1 if high else 1
    best = min(cands, key=lambda c: (sign * c[0], c[1]))
    return best, sum(1 for c in cands if c[0] == best[0]) - 1


def _num(x: float, places: int = 1) -> str:
    s = f"{x:.{places}f}"
    return s[1:] if s.startswith("-") and float(s) == 0 else s


def _poss(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")


def _award(key: str, team: int, value: float, detail: str, *, opponent: int | None,
           player: dict | None = None, tied: int = 0) -> dict:
    return {"key": key, "title": TITLES[key], "team": team, "value": round(value, 2),
            "detail": detail, "opponent": opponent, "player": player, "tied": tied}


# ── team awards ────────────────────────────────────────────────────────────────
def _team_awards(sides: list[Side], who) -> list[dict]:
    """Top dog, toilet bowl, blowout, nail-biter, robbed, stole one."""
    winners = [s for s in sides if s.score > s.opp_score]
    losers = [s for s in sides if s.score < s.opp_score]

    def margin(s: Side) -> float:
        return round(abs(s.score - s.opp_score), 2)

    def vs(s: Side) -> str:
        return f"{_num(s.score)} vs {_poss(who(s.opp))} {_num(s.opp_score)}"

    def won(s: Side, places: int = 1) -> str:
        return f"Won {_num(s.score, places)} to {_poss(who(s.opp))} {_num(s.opp_score, places)}"

    def lost(s: Side) -> str:
        return f"Lost {_num(s.score)} to {_poss(who(s.opp))} {_num(s.opp_score)}"

    specs = (
        ("top_dog", sides, lambda s: s.score, True, vs),
        ("toilet_bowl", sides, lambda s: s.score, False, vs),
        ("blowout", winners, margin, True, won),
        ("nail_biter", winners, margin, False, lambda s: won(s, 2)),
        ("robbed", losers, lambda s: s.score, True, lost),
        ("stole_one", winners, lambda s: s.score, False, won),
    )
    out = []
    for key, pool, value, high, detail in specs:
        got = _pick([(value(s), (s.team,), s) for s in pool], high=high)
        if got:
            (v, _tb, s), tied = got
            out.append(_award(key, s.team, v, detail(s), opponent=s.opp, tied=tied))
    return out


def _startable(ctx, w: int, team: int, roster) -> set[str]:
    """Roster players who could have been started (``ReportContext.startable``: not picked
    up after their game kicked off). Every roster player when ctx can't tell."""
    fn = getattr(ctx, "startable", None)
    return fn(w, team) if callable(fn) else set(roster.players)


def _bench_warmer(ctx, w: int, sides: list[Side], who) -> dict | None:
    """Most points between the actual score and the best possible lineup."""
    cands: list[Cand] = []
    for s in sides:
        roster = ctx.rosters.get(w, {}).get(s.team)
        if roster is None:
            continue
        best = round(float(ctx.lu.best(_startable(ctx, w, s.team, roster), w)), 2)
        left = round(best - s.score, 2)
        if left > 0:
            cands.append((left, (s.team,), (s, best)))
    got = _pick(cands, high=True)
    if not got:
        return None
    (left, _tb, (s, best)), tied = got
    return _award("bench_warmer", s.team, left,
                  f"Scored {_num(s.score)}; the best lineup was {_num(best)}", opponent=s.opp, tied=tied)


# ── player awards ──────────────────────────────────────────────────────────────
def _pos(ctx, roster, pid: str) -> str:
    return ctx.pos.get(pid) or roster.players.get(pid, ("", ""))[1] or "?"


def _player(ctx, roster, pid: str) -> dict:
    name = roster.players[pid][0] if pid in roster.players else ctx.names.get(pid, f"Player {pid}")
    return {"id": pid, "name": name, "pos": _pos(ctx, roster, pid), "pro_team": ctx.pro.get(pid, "")}


def _fits(ids: list[str], eligible: dict[str, list[str]], slots: dict[str, int]) -> bool:
    """Can every player in ``ids`` start at once (each in a distinct slot he's eligible
    for)? Bipartite matching over the league's starting slots."""
    seats = [s for s, n in slots.items() for _ in range(n)]
    taken: dict[int, str] = {}

    def place(pid: str, seen: set[int]) -> bool:
        for k, slot in enumerate(seats):
            if k in seen or slot not in (eligible.get(pid) or ()):
                continue
            seen.add(k)
            if k not in taken or place(taken[k], seen):
                taken[k] = pid
                return True
        return False

    return all(place(pid, set()) for pid in ids)


def _best_swap(ctx, roster, started: dict, bench: dict):
    """The biggest single start/sit mistake: a benched player who outscored a starter he
    could legally have replaced (ESPN slot eligibility, so a TE can take a WR's FLEX
    spot). Falls back to same-position swaps if eligibility data doesn't fit the real
    lineup. Returns ``((bench pts, id), (starter pts, id))`` or None."""
    starters = [x for xs in started.values() for x in xs]
    benched = [x for xs in bench.values() for x in xs]
    elig, slots = getattr(ctx.lu, "eligible", {}), getattr(ctx.lu, "slots", {})
    ids = [pid for _p, pid in starters]
    if slots and _fits(ids, elig, slots):
        legal = lambda b, st: _fits([i for i in ids if i != st[1]] + [b[1]], elig, slots)  # noqa: E731
    else:
        pos_of = {pid: pos for pos, xs in {**started, **bench}.items() for _p, pid in xs}
        legal = lambda b, st: pos_of.get(b[1]) == pos_of.get(st[1]) != "?"  # noqa: E731
    best = None
    for b in sorted(benched, key=lambda x: (-x[0], x[1])):
        for st in sorted(starters, key=lambda x: (x[0], x[1])):
            gap = b[0] - st[0]
            if gap <= 0 or (best and gap <= best[0][0] - best[1][0]):
                break
            if legal(b, st):
                best = (b, st)
                break
    return best


def _player_awards(ctx, w: int, sides: list[Side]) -> list[dict]:
    """MVP, dud and the week's biggest bench blunder."""
    pts = ctx.pts.get(w, {})
    mvp: list[Cand] = []
    dud: list[Cand] = []
    blunder: list[Cand] = []
    for s in sides:
        roster = ctx.rosters.get(w, {}).get(s.team)
        if roster is None:
            continue
        started: dict[str, list[tuple[float, str]]] = defaultdict(list)
        bench: dict[str, list[tuple[float, str]]] = defaultdict(list)
        could_start = _startable(ctx, w, s.team, roster)
        for pid in roster.players:
            p = round(float(pts.get(pid, 0.0)), 2)
            pos = _pos(ctx, roster, pid)
            if pid in roster.started:
                started[pos].append((p, pid))
                mvp.append((p, (-s.score, s.team, pid), (s, pid)))
                if pos not in NO_DUD_POSITIONS:
                    dud.append((p, (s.score, s.team, pid), (s, pid)))
            elif pid in could_start:  # someone picked up after his game can't be a blunder
                bench[pos].append((p, pid))
        swap = _best_swap(ctx, roster, started, bench)
        if swap:
            b, st = swap
            blunder.append((round(b[0] - st[0], 2), (s.score, s.team, b[1]), (s, b, st)))

    out = []
    got = _pick(mvp, high=True)
    if got:
        (v, _tb, (s, pid)), tied = got
        roster = ctx.rosters[w][s.team]
        p = _player(ctx, roster, pid)
        out.append(_award("mvp", s.team, v, _label(p), opponent=s.opp, player=p, tied=tied))
    got = _pick(dud, high=False)
    if got:
        (v, _tb, (s, pid)), tied = got
        p = _player(ctx, ctx.rosters[w][s.team], pid)
        out.append(_award("dud", s.team, v, f"Started {_label(p)} for {_num(v)}",
                          opponent=s.opp, player=p, tied=tied))
    got = _pick(blunder, high=True)
    if got:
        (gap, _tb, (s, b, st)), tied = got
        roster = ctx.rosters[w][s.team]
        p = _player(ctx, roster, b[1])
        starter = _player(ctx, roster, st[1])
        out.append(_award("bench_blunder", s.team, gap,
                          f"Benched {p['name']} ({_num(b[0])}) for {starter['name']} ({_num(st[0])})",
                          opponent=s.opp, player=p, tied=tied))
    return out


def _label(p: dict) -> str:
    """'Josh Allen (QB, KC)' — position and NFL team, whichever we know."""
    meta = ", ".join(x for x in (p["pos"], p["pro_team"]) if x and x != "?")
    return f"{p['name']} ({meta})" if meta else p["name"]


# ── the report ─────────────────────────────────────────────────────────────────
def _week_awards(ctx, w: int, who) -> list[dict]:
    sides = _sides(ctx.matchups.get(w, []))
    if not sides:
        return []
    found = _team_awards(sides, who)
    bw = _bench_warmer(ctx, w, sides, who)
    if bw:
        found.append(bw)
    found += _player_awards(ctx, w, sides)
    order = list(TITLES)
    return sorted(found, key=lambda a: order.index(a["key"]))


def _season(teams: list[dict], weeks: list[dict]) -> list[dict]:
    """Award counts per team, zeros included."""
    counts: dict[int, dict[str, int]] = {int(t["id"]): dict.fromkeys(TITLES, 0) for t in teams}
    for wk in weeks:
        for a in wk["awards"]:
            counts.setdefault(a["team"], dict.fromkeys(TITLES, 0))[a["key"]] += 1
    return [{"team": tid, "counts": c} for tid, c in sorted(counts.items())]


def build(ctx) -> dict | None:
    """``{"weeks": [{"week", "awards": [...]}], "season": [{"team", "counts"}]}``."""
    names = {int(t["id"]): (t.get("manager") or t.get("name") or f"Team {t['id']}") for t in ctx.teams}

    def who(tid: int) -> str:
        return names.get(tid, f"Team {tid}")

    weeks = []
    for w in ctx.weeks:
        found = _week_awards(ctx, w, who)
        if found:
            weeks.append({"week": w, "awards": found})
    return {"weeks": weeks, "season": _season(ctx.teams, weeks)}
