"""Shame streaks: the embarrassing runs still going after the last finished week
(losing streaks, low scores, bench blunders, ...). Output: ``window.LEAGUE_DATA.streaks``.

What counts
    Only regular-season weeks (week <= ``ctx.reg_weeks``; every week if the season length
    is unknown) in which a team actually played a game. Each of those weeks is checked
    against six rules (``KINDS``):

    loss        Lost its game: score below the opponent's. A tie is not a loss and ends a run.
    under120    Scored under 120 ("Shameful").
    sub100      Scored under 100 ("Utter disgust"; the page has a cruder name in R-rated mode).
                Every sub100 week is also an under120 week.
    blunder     The team's biggest start/sit miss that week is 15+ points: a benched player
                outscored a starter he could legally have replaced (``awards._best_swap``).
                Only players the team could really have started count (``ctx.startable``:
                someone picked up after his game kicked off can't be a blunder).
    under_proj  Scored less than ESPN's pregame projection, which is the sum of
                ``ctx.proj[week]`` over that week's starters. If any starter has no projection
                (or the total is 0) there is no data for that week: it isn't flagged and it
                ends a run, rather than guessing.
    dud         Started a QB, RB, WR or TE (by ``ctx.pos``) who scored under 3 points.

Streaks
    A streak is a run of consecutive flagged weeks in the team's own played-week order (a week
    the team didn't play, like a bye, is skipped rather than counted as a break).
    It is *active* when it ends at the team's most recent played week, and it only counts
    (is listed under ``active`` and ``teams``) once it reaches the kind's minimum length.
    ``records`` holds each kind's longest run of the season (also at least the minimum:
    a lone dud isn't a streak). Every team that holds that length is listed once (its latest
    such run), with the weeks it covered and whether it is still going.

Output (JSON-ready)::

    {"through": last regular-season week with a game,
     "kinds":   [{"key", "title", "what", "min"}],
     "active":  [{"team", "key", "length", "since_week", "detail"}],   # detail: the latest week
     "records": [{"key", "team", "length", "from_week", "to_week", "active"}],
     "teams":   [{"team", "active": {key: length}}],                   # every team that played
     "lowest_score": {"team", "week", "score"}}                        # lowest team score so far

``None`` when no regular-season game has been played yet.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from league import awards

UNDER_120 = 120.0
UNDER_100 = 100.0
BLUNDER_POINTS = 15.0
DUD_POINTS = 3.0
DUD_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})

# (key, title, what, minimum run length that counts as a streak). Order is the display order.
KINDS: tuple[tuple[str, str, str, int], ...] = (
    ("loss", "Losing streak", "Losses in a row.", 2),
    ("under120", "Shameful", "Weeks in a row scoring under 120.", 2),
    ("sub100", "Utter disgust", "Weeks in a row scoring under 100.", 1),
    ("blunder", "Bench blunders",
     "Weeks in a row a benched player outscored the starter he could have replaced by 15 or more points.", 2),
    ("under_proj", "Under the projection", "Weeks in a row scoring less than ESPN projected.", 3),
    ("dud", "Duds in the lineup",
     "Weeks in a row starting a QB, RB, WR or TE who scored under 3 points.", 2),
)
MIN_LENGTH = {key: low for key, _title, _what, low in KINDS}


@dataclass(frozen=True)
class Game:
    """One team's side of a played regular-season game."""
    week: int
    team: int
    score: float
    opp: int
    opp_score: float


@dataclass(frozen=True)
class Run:
    """A maximal run of flagged weeks for one team and kind."""
    key: str
    team: int
    first: int       # first week of the run
    last: int        # last week of the run
    length: int
    active: bool     # ends at the team's most recent played week
    detail: str      # what happened in ``last``


def _n(x: float) -> str:
    s = f"{x:.1f}"
    return "0.0" if s == "-0.0" else s


def _pair(a: float, b: float) -> tuple[str, str]:
    """Two numbers to one decimal, or to the cent when that would make them look equal."""
    x, y = _n(a), _n(b)
    return (x, y) if x != y or a == b else (f"{a:.2f}", f"{b:.2f}")


def _below(x: float, line: float) -> str:
    """``x``, known to be under ``line``, to one decimal, or to the cent when rounding would
    show it at the line (99.99 must not read as "100.0" in an under-100 streak)."""
    shown = _n(x)
    return shown if float(shown) < line else f"{x:.2f}"


def _poss(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")


def _runs(key: str, team: int, games: list[Game], details: list[str | None]) -> list[Run]:
    """Maximal runs of non-None ``details`` (one per played game, oldest first)."""
    out: list[Run] = []
    start = None
    for i, d in enumerate([*details, None]):  # the trailing None closes a run that is still going
        if d is not None and start is None:
            start = i
        elif d is None and start is not None:
            end = i - 1
            out.append(Run(key, team, games[start].week, games[end].week, end - start + 1,
                           end == len(games) - 1, details[end]))
            start = None
    return out


def _games(ctx) -> dict[int, list[Game]]:
    """Every team's played regular-season games, oldest week first."""
    reg = getattr(ctx, "reg_weeks", 0) or None  # 0/None: season length unknown, so no cutoff
    out: dict[int, list[Game]] = defaultdict(list)
    for w in sorted(ctx.weeks):
        if reg and w > reg:
            continue
        for g in ctx.matchups.get(w, []):
            home, away = int(g["home"]), int(g["away"])
            hs, as_ = round(float(g["home_score"]), 2), round(float(g["away_score"]), 2)
            out[home].append(Game(w, home, hs, away, as_))
            out[away].append(Game(w, away, as_, home, hs))
    return out


def _name(ctx, roster, pid: str) -> str:
    if pid in roster.players:
        return roster.players[pid][0]
    return ctx.names.get(pid, f"Player {pid}")


def _projection(ctx, w: int, roster) -> float | None:
    """ESPN's pregame projection for the week's starters, or None when any starter lacks one."""
    proj = (getattr(ctx, "proj", None) or {}).get(w) or {}
    if not roster.started or any(proj.get(pid) is None for pid in roster.started):
        return None
    total = round(sum(float(proj[pid]) for pid in roster.started), 2)
    return total if total > 0 else None


def _lineup_flags(ctx, g: Game, roster) -> dict[str, str]:
    """blunder, under_proj and dud for one team-week, with the detail line for each."""
    w, pts = g.week, ctx.pts.get(g.week, {})
    could_start = awards._startable(ctx, w, g.team, roster)
    started: dict[str, list[tuple[float, str]]] = defaultdict(list)
    bench: dict[str, list[tuple[float, str]]] = defaultdict(list)
    duds: list[tuple[float, str]] = []
    for pid in roster.players:
        p = round(float(pts.get(pid, 0.0)), 2)
        pos = awards._pos(ctx, roster, pid)
        if pid in roster.started:
            started[pos].append((p, pid))
            if pos in DUD_POSITIONS and p < DUD_POINTS:
                duds.append((p, pid))
        elif pid in could_start:  # someone picked up after his game can't be a blunder
            bench[pos].append((p, pid))
    out: dict[str, str] = {}
    swap = awards._best_swap(ctx, roster, started, bench)
    if swap and round(swap[0][0] - swap[1][0], 2) >= BLUNDER_POINTS:
        (bp, bid), (sp, sid) = swap
        out["blunder"] = (f"Benched {_name(ctx, roster, bid)} ({_n(bp)}) "
                          f"for {_name(ctx, roster, sid)} ({_n(sp)})")
    expected = _projection(ctx, w, roster)
    if expected is not None and g.score < expected:
        mine, theirs = _pair(g.score, expected)
        out["under_proj"] = f"Scored {mine} vs ESPN's {theirs}"
    if duds:
        p, pid = min(duds)
        out["dud"] = f"Started {_name(ctx, roster, pid)} ({_below(p, DUD_POINTS)})"
    return out


def _flags(ctx, g: Game, who) -> dict[str, str]:
    """Every kind this team-week trips, mapped to its detail line."""
    out: dict[str, str] = {}
    if g.score < g.opp_score:
        mine, theirs = _pair(g.score, g.opp_score)
        out["loss"] = f"Lost {mine} to {_poss(who(g.opp))} {theirs}"
    if g.score < UNDER_120:
        out["under120"] = f"Scored {_below(g.score, UNDER_120)}"
    if g.score < UNDER_100:
        out["sub100"] = f"Scored {_below(g.score, UNDER_100)}"
    roster = ctx.rosters.get(g.week, {}).get(g.team)
    if roster is not None:
        out.update(_lineup_flags(ctx, g, roster))
    return out


def build(ctx) -> dict | None:
    """See the module docstring for the rules and the output shape."""
    games = _games(ctx)
    if not games:
        return None
    names = {int(t["id"]): (t.get("manager") or t.get("name") or f"Team {t['id']}") for t in ctx.teams}

    def who(tid: int) -> str:
        return names.get(tid, f"Team {tid}")

    runs: list[Run] = []
    for team, played in sorted(games.items()):
        flags = [_flags(ctx, g, who) for g in played]
        for key, *_rest in KINDS:
            runs += _runs(key, team, played, [f.get(key) for f in flags])

    order = {key: i for i, (key, *_rest) in enumerate(KINDS)}
    counts = [r for r in runs if r.length >= MIN_LENGTH[r.key]]
    active = sorted((r for r in counts if r.active), key=lambda r: (order[r.key], -r.length, r.team))

    records = []
    for key, *_rest in KINDS:
        mine = [r for r in counts if r.key == key]
        longest = max((r.length for r in mine), default=0)
        holders: dict[int, Run] = {}  # one entry per team: its latest run of the record length
        for r in mine:
            if r.length == longest and (r.team not in holders or r.first > holders[r.team].first):
                holders[r.team] = r
        records += [{"key": key, "team": team, "length": r.length, "from_week": r.first,
                     "to_week": r.last, "active": r.active} for team, r in sorted(holders.items())]

    score, week, team = min((g.score, g.week, g.team) for played in games.values() for g in played)
    return {
        "through": max(g.week for played in games.values() for g in played),
        "kinds": [{"key": key, "title": title, "what": what, "min": low}
                  for key, title, what, low in KINDS],
        "active": [{"team": r.team, "key": r.key, "length": r.length, "since_week": r.first,
                    "detail": r.detail} for r in active],
        "records": records,
        "teams": [{"team": t, "active": {r.key: r.length for r in active if r.team == t}}
                  for t in sorted(games)],
        "lowest_score": {"team": team, "week": week, "score": score},
    }
