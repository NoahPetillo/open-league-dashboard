"""Power rankings: every team ranked after every completed week, plus a one-line
blurb per team for the latest week.

Power score (0-100), as of week k:
    50%  all-play win % through week k (each week, a team's score against every
         other team's score that week; ties count half)
    30%  recent form: average score over weeks max(1, k-2)..k, scaled across the
         league as (x - min) / (max - min) * 100 (everyone gets 50 if all are equal)
    20%  actual win % through week k (equal scores = a tie = half a win)
Ranked by score; ties go to points for through week k, then team id.

``build(ctx)`` returns::

    {"method": "...",
     "weeks": [{"week": k, "teams": [{"team", "rank", "score", "change", "record",
                                      "allplay", "allplay_pct", "form_avg", "win_pct"}, ...]}],
     "blurbs": [{"team", "text"}, ...]}

``change`` is places gained vs the previous week (positive = moved up, None in week 1);
``allplay_pct`` and ``win_pct`` are fractions (0-1); ``form_avg`` is the unscaled
average score over the form window. Everything is derived from ``ctx.matchups``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

METHOD = "50% all-play record, 30% last three weeks of scoring, 20% actual record"
W_ALLPLAY, W_FORM, W_RECORD = 0.5, 0.3, 0.2
FORM_WEEKS = 3
LUCK_GAP = 1.25        # wins above/below what the all-play record predicts before we call it luck
BLURB_KIND_CAP = 2     # most teams that may share one kind of blurb
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
                10: "ten"}


# ── reading the matchups ───────────────────────────────────────────────────────
@dataclass
class _Season:
    through: int
    ids: list[int]
    names: dict[int, str]
    scores: dict[int, dict[int, float]]                   # week → team → score
    games: dict[int, dict[int, tuple[int, float, float]]]  # week → team → (opponent, mine, theirs)


def _read_season(ctx) -> _Season:
    """Scores and results by week, from the box-score matchups of the completed weeks."""
    through = int(ctx.through)
    reg_weeks = int(getattr(ctx, "reg_weeks", 0) or 0)
    if reg_weeks:
        through = min(through, reg_weeks)  # playoff weeks leave teams without games, so ranks stop with the regular season
    names = {t["id"]: t.get("name") or f"Team {t['id']}" for t in ctx.teams}
    scores: dict[int, dict[int, float]] = {}
    games: dict[int, dict[int, tuple[int, float, float]]] = {}
    for w in range(1, through + 1):
        scores[w], games[w] = {}, {}
        for m in ctx.matchups.get(w, []):
            home, away = m["home"], m["away"]
            hs, as_ = float(m["home_score"]), float(m["away_score"])
            scores[w][home], scores[w][away] = hs, as_
            games[w][home], games[w][away] = (away, hs, as_), (home, as_, hs)
            names.setdefault(home, f"Team {home}")
            names.setdefault(away, f"Team {away}")
    return _Season(through, sorted(names), names, scores, games)


def _outcome(mine: float, theirs: float) -> str:
    return "W" if mine > theirs else "L" if mine < theirs else "T"


# ── the formula ────────────────────────────────────────────────────────────────
def _pct(w: float, losses: float, t: float) -> float | None:
    """Win fraction with ties as half a win; None when nothing was played."""
    games = w + losses + t
    return (w + t / 2) / games if games else None


def _all_play_week(scores: dict[int, float]) -> dict[int, tuple[int, int, int]]:
    """Each team's (wins, losses, ties) against every other team's score that week."""
    out = {}
    for tid, s in scores.items():
        beat = sum(1 for o, x in scores.items() if o != tid and x < s)
        tied = sum(1 for o, x in scores.items() if o != tid and x == s)
        out[tid] = (beat, len(scores) - 1 - beat - tied, tied)
    return out


def _form_window(through: int) -> range:
    return range(max(1, through - FORM_WEEKS + 1), through + 1)


def _scale(values: dict[int, float | None]) -> dict[int, float]:
    """(x - min) / (max - min) * 100 across the league; 50 for everyone if all are equal."""
    present = [v for v in values.values() if v is not None]
    if not present or max(present) == min(present):
        return dict.fromkeys(values, 50.0)
    lo, hi = min(present), max(present)
    return {t: 50.0 if v is None else (v - lo) / (hi - lo) * 100 for t, v in values.items()}


def power_score(allplay_pct: float | None, form_scaled: float, win_pct: float | None) -> float:
    """0-100. A team with nothing played yet counts as .500 (50)."""
    ap = 0.5 if allplay_pct is None else allplay_pct
    wp = 0.5 if win_pct is None else win_pct
    return W_ALLPLAY * 100 * ap + W_FORM * form_scaled + W_RECORD * 100 * wp


@dataclass
class _Row:
    """One team's standing in the power rankings, unrounded."""
    team: int
    rank: int
    score: float
    record: tuple[int, int, int]
    allplay: tuple[int, int, int]
    pf: float
    form: float | None
    allplay_pct: float | None
    win_pct: float | None


def _week_table(season: _Season, k: int) -> list[_Row]:
    """Every team's power score and rank as of week ``k``, best first."""
    rec = {t: [0, 0, 0] for t in season.ids}
    ap = {t: [0, 0, 0] for t in season.ids}
    pf = dict.fromkeys(season.ids, 0.0)
    for w in range(1, k + 1):
        for tid, (_o, mine, theirs) in season.games[w].items():
            rec[tid]["WLT".index(_outcome(mine, theirs))] += 1
        for tid, (a, b, c) in _all_play_week(season.scores[w]).items():
            ap[tid][0] += a
            ap[tid][1] += b
            ap[tid][2] += c
        for tid, s in season.scores[w].items():
            pf[tid] += s
    form: dict[int, float | None] = {}
    for tid in season.ids:
        vals = [season.scores[w][tid] for w in _form_window(k) if tid in season.scores[w]]
        form[tid] = sum(vals) / len(vals) if vals else None
    scaled = _scale(form)
    rows = []
    for tid in season.ids:
        app, wp = _pct(*ap[tid]), _pct(*rec[tid])
        rows.append(_Row(tid, 0, power_score(app, scaled[tid], wp), tuple(rec[tid]), tuple(ap[tid]),
                         pf[tid], form[tid], app, wp))
    rows.sort(key=lambda r: (-round(r.score, 6), -round(r.pf, 6), r.team))
    for i, r in enumerate(rows):
        r.rank = i + 1
    return rows


def _fmt_record(rec: tuple[int, int, int]) -> str:
    w, losses, t = rec
    return f"{w}-{losses}" + (f"-{t}" if t else "")


def _public(rows: list[_Row], prev: dict[int, int]) -> list[dict]:
    return [{"team": r.team, "rank": r.rank, "score": round(r.score, 1),
             "change": prev[r.team] - r.rank if r.team in prev else None,
             "record": _fmt_record(r.record), "allplay": _fmt_record(r.allplay),
             "allplay_pct": None if r.allplay_pct is None else round(r.allplay_pct, 4),
             "form_avg": None if r.form is None else round(r.form, 2),
             "win_pct": None if r.win_pct is None else round(r.win_pct, 4)} for r in rows]


# ── blurbs ─────────────────────────────────────────────────────────────────────
@dataclass
class _Fact:
    kind: str       # which template family; used to keep the blurbs varied
    priority: int
    text: str


def _f1(x: float) -> str:
    """One decimal, rounded half-up exactly like the site's f1() so numbers match."""
    return f"{math.floor(x * 10 + 0.5) / 10:.1f}"


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _word(n: int) -> str:
    return NUMBER_WORDS.get(n, str(n))


def _streak(season: _Season, team: int, k: int) -> tuple[str, int]:
    """The team's current run of W or L (a tie breaks it); byes are skipped."""
    kind, n = "", 0
    for w in range(k, 0, -1):
        g = season.games[w].get(team)
        if g is None:
            continue
        res = _outcome(g[1], g[2])
        kind = kind or res
        if res != kind:
            break
        n += 1
    return (kind, n) if kind in ("W", "L") else ("", 0)


def _extreme_run(season: _Season, team: int, k: int, high: bool) -> int:
    """Consecutive weeks ending at ``k`` with the league's single highest (or lowest) score."""
    n = 0
    for w in range(k, 0, -1):
        s = season.scores[w]
        others = [x for t, x in s.items() if t != team]
        if team not in s or not others:
            break
        if not all((s[team] > x) if high else (s[team] < x) for x in others):
            break
        n += 1
    return n


def _drought(season: _Season, team: int, k: int) -> tuple[int, int] | None:
    """(week, mark): the longest stretch, at least two weeks, with no score at or above
    ``mark``, a multiple of 10, since ``week``. None if the team has no such stretch."""
    for n in range(1, k - 1):
        later = [season.scores[w][team] for w in range(n + 1, k + 1) if team in season.scores[w]]
        if team not in season.scores[n] or not later:
            continue
        mark = (math.floor(max(later) / 10) + 1) * 10
        if season.scores[n][team] >= mark:
            return n, mark
    return None


def _run_at(tables: dict[int, list[_Row]], team: int, k: int, rank: int | None) -> int:
    """Consecutive weeks ending at ``k`` the team held ``rank`` (None = last place)."""
    n = 0
    for w in range(k, 0, -1):
        rows = tables[w]
        mine = next((r.rank for r in rows if r.team == team), None)
        if mine != (len(rows) if rank is None else rank):
            break
        n += 1
    return n


def _week_facts(season: _Season, team: int, k: int, add) -> None:
    """Facts about how the team did in the latest week."""
    game = season.games[k].get(team)
    if game is None:
        return
    opp, mine, theirs = game
    res = _outcome(mine, theirs)
    s = _f1(mine)
    others = [x for t, x in season.scores[k].items() if t != team]
    higher, lower = sum(x > mine for x in others), sum(x < mine for x in others)
    clear = len(others) > 0 and higher + lower == len(others)  # nobody tied with them
    if clear:
        high_run = _extreme_run(season, team, k, True)
        low_run = _extreme_run(season, team, k, False)
        if high_run >= 2:
            add("high", 93, f"Highest score in the league {_word(high_run)} weeks running ({s} this week)")
        elif higher == 0:  # the week's top score always wins its game
            add("high", 90, f"Highest score of the week ({s})")
        elif higher <= 3 and res == "L":
            add("bad-beat", 80 - 4 * (higher - 1), f"Lost with the {_ordinal(higher + 1)}-highest score of the week ({s})")
        if low_run >= 2:
            add("low", 92, f"Lowest score in the league {_word(low_run)} weeks running ({s} this week)")
        elif lower == 0:  # ...and the bottom score always loses
            add("low", 85, f"Lowest score of the week ({s})")
        elif lower <= 3 and res == "W":
            add("lucky-win", 80 - 4 * (lower - 1), f"Won with the {_ordinal(lower + 1)}-lowest score of the week ({s})")
    own = [x for w in range(1, k) if (x := season.scores[w].get(team)) is not None]
    if k >= 3 and len(own) >= 2:
        last = season.scores[k - 1].get(team)
        delta = "" if last is None else f"{'up' if mine > last else 'down'} {_f1(abs(mine - last))}"
        if mine > max(own):
            add("season", 60, f"Season-high {s}" + (f", {delta} on last week" if delta else ""))
        elif mine < min(own):
            add("season", 58, f"Season-low {s}" + (f", {delta} on last week" if delta else ""))
    margin = abs(mine - theirs)
    if res != "T" and margin < 3:
        add("margin", 66 if margin < 1 else 62, f"{'Won' if res == 'W' else 'Lost'} by {_f1(margin)} points")
    elif res != "T" and margin >= 50:
        add("margin", 55 if res == "W" else 58, f"{'Won' if res == 'W' else 'Lost'} by {_f1(margin)} points")
    them = season.names[opp]
    add("result", 10, {"W": f"Won {s}-{_f1(theirs)} over {them}", "L": f"Lost {s}-{_f1(theirs)} to {them}",
                       "T": f"Tied {them} at {s}"}[res])


def _record_facts(season: _Season, team: int, k: int, row: _Row, rows: list[_Row], add) -> None:
    """Facts about the season so far: streaks, luck, all-play, droughts, form, points."""
    w, losses, t = row.record
    gp = w + losses + t
    kind, n = _streak(season, team, k)
    if kind and n >= 2:
        add("streak", 88 if n >= 4 else 78 if n == 3 else 35, f"{'Won' if kind == 'W' else 'Lost'} {n} straight")
    if gp >= 3 and losses == 0 and t == 0:
        add("streak", 89, f"Still unbeaten at {_fmt_record(row.record)}")
    if gp >= 3 and w == 0 and t == 0:
        add("streak", 89, f"Still winless at {_fmt_record(row.record)}")

    ap = _fmt_record(row.allplay)
    if gp >= 3 and row.allplay_pct is not None:
        luck = w + t / 2 - row.allplay_pct * gp
        rec = _fmt_record(row.record)
        if luck >= LUCK_GAP:
            add("luck", 70 + min(14, round(luck * 4)), f"{rec} on a {ap} all-play. Living on luck")
        elif luck <= -LUCK_GAP:
            add("luck", 70 + min(14, round(-luck * 4)), f"{rec} on a {ap} all-play. The schedule has been cruel")
        elif row.allplay_pct >= 0.75:
            add("allplay", 74, f"All-play {ap}. The real deal")
        elif row.allplay_pct <= 0.25:
            add("allplay", 72, f"All-play {ap}. Not unlucky, just bad")

    found = _drought(season, team, k) if k >= 3 else None
    if found:
        since, mark = found
        add("drought", min(82, 62 + 5 * (k - since)), f"Hasn't cracked {mark} since week {since}")

    forms = [r.form for r in rows if r.form is not None]
    if k >= 2 and row.form is not None and len(forms) > 1:
        span = "three weeks" if k >= FORM_WEEKS else f"{k} weeks"
        if row.form == max(forms) and forms.count(row.form) == 1:
            add("form", 68, f"Hottest team: {_f1(row.form)} a week over the last {span}")
        elif row.form == min(forms) and forms.count(row.form) == 1:
            add("form", 66, f"Coldest team: {_f1(row.form)} a week over the last {span}")

    pfs = [r.pf for r in rows]
    if k >= 2:
        higher_pf = sum(x > row.pf for x in pfs)
        if higher_pf == 0 and pfs.count(row.pf) == 1:
            add("pf", 50, f"Most points scored this season ({_f1(row.pf)})")
        elif row.pf == min(pfs) and pfs.count(row.pf) == 1:
            add("pf", 50, f"Fewest points scored this season ({_f1(row.pf)})")
        add("pfrank", 8, f"{_ordinal(higher_pf + 1)} in points scored ({_f1(row.pf)})")
    add("record", 5, f"{_fmt_record(row.record)} record, {ap} all-play")


def _rank_facts(season: _Season, team: int, k: int, tables: dict[int, list[_Row]], row: _Row, add) -> None:
    """Facts about movement and about holding the top or bottom spot."""
    n = len(tables[k])
    if k >= 2:
        before = next((r.rank for r in tables[k - 1] if r.team == team), None)
        game = season.games[k].get(team)
        if before is not None and game is not None and before != row.rank:
            moved = abs(before - row.rank)
            med = sorted(season.scores[k].values())
            median = (med[(len(med) - 1) // 2] + med[len(med) // 2]) / 2
            s = _f1(game[1])
            if moved >= 2:
                pri = 87 if moved >= 4 else 76 if moved == 3 else 55
                if row.rank < before:
                    text = (f"Up {moved} spots after dropping {s}" if game[1] >= median
                            else f"Up {moved} spots despite scoring just {s}")
                else:
                    text = (f"Down {moved} spots despite scoring {s}" if game[1] >= median
                            else f"Down {moved} spots after scoring just {s}")
                add("move", pri, text)
        if row.rank == 1 and before not in (None, 1):
            old = next((r.team for r in tables[k - 1] if r.rank == 1), None)
            add("rank", 80, f"Takes over No. 1 from {season.names[old]}" if old is not None else "New No. 1")
        elif row.rank == n and before not in (None, n):
            add("rank", 60, f"Falls to last, down from {_ordinal(before)}")
    top = _run_at(tables, team, k, 1)
    if top >= 2:
        add("rank", 66 + min(10, 3 * (top - 2)), f"Atop the rankings {_word(top)} weeks running")
    bottom = _run_at(tables, team, k, None)
    if bottom >= 2:
        add("rank", 64 + min(10, 3 * (bottom - 2)), f"Stuck at the bottom {_word(bottom)} weeks running")


def _facts(season: _Season, tables: dict[int, list[_Row]], team: int) -> list[_Fact]:
    """Every true, notable thing about this team as of the latest week."""
    k = season.through
    rows = tables[k]
    row = next(r for r in rows if r.team == team)
    out: list[_Fact] = []

    def add(kind: str, priority: int, text: str) -> None:
        out.append(_Fact(kind, priority, text))

    _week_facts(season, team, k, add)
    _record_facts(season, team, k, row, rows, add)
    _rank_facts(season, team, k, tables, row, add)
    return sorted(out, key=lambda f: -f.priority)


def _blurbs(season: _Season, tables: dict[int, list[_Row]]) -> list[dict]:
    """One line per team: its most notable fact, but no more than BLURB_KIND_CAP teams
    share a kind (the team with the better fact keeps it)."""
    latest = tables[season.through]
    facts = {r.team: _facts(season, tables, r.team) for r in latest}
    used: dict[str, int] = {}
    chosen: dict[int, str] = {}
    for tid in sorted(facts, key=lambda t: (-facts[t][0].priority, t)):
        pick = next((f for f in facts[tid] if used.get(f.kind, 0) < BLURB_KIND_CAP), facts[tid][0])
        used[pick.kind] = used.get(pick.kind, 0) + 1
        chosen[tid] = pick.text
    return [{"team": r.team, "text": chosen[r.team]} for r in latest]


# ── entry point ────────────────────────────────────────────────────────────────
def build(ctx) -> dict | None:
    season = _read_season(ctx)
    if season.through < 1 or not season.ids:
        return None
    tables = {k: _week_table(season, k) for k in range(1, season.through + 1)}
    weeks, prev = [], {}
    for k in range(1, season.through + 1):
        weeks.append({"week": k, "teams": _public(tables[k], prev)})
        prev = {r.team: r.rank for r in tables[k]}
    return {"method": METHOD, "weeks": weeks, "blurbs": _blurbs(season, tables)}
