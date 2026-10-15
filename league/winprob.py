"""Win probability from ESPN projections: the Sunday recap (how every matchup swung as the
week's games finished) and the upset alert (this week's pregame odds).

``build(ctx)`` → ``window.LEAGUE_DATA.recap`` (completed weeks).
``live(live_data)`` → ``window.LIVE_DATA.winprob`` (the week in progress, from league/live.py).

The model
---------
Measured on this league's weeks 1-4 (n=48 team-weeks): a team's actual score minus ESPN's
projection has sd 24.3. Per player the miss grows with the projection.

* Each starter still to play counts his ESPN projection, give or take: QB/RB/WR/TE
  sd = 3 + 0.35 x projection; K 5.7; HC 4.5; anything else (IDP positions like LB/DE/DT/S/CB,
  D/ST, P) 3.0. A starter projected exactly 0 (out, or no game) has sd 0. Summing these gives
  a team sd of about 25 on weeks 1-4 (25.4 rms), a touch wider than the 24.3 observed.
* A team's mean = points already banked + projections of starters still to play; variance =
  sum of sd^2. P(A beats B) = Phi((muA - muB) / sqrt(varA + varB)); with zero variance it is
  1, 0 or 0.5 by the sign.
* ESPN's projections have been a coin flip here (the favorites' record is in the output), so
  the pages say so.

Slates and checkpoints
----------------------
There is no in-game history, so the swing is measured between "slates" of games. Take the
kickoff of every starter in the league that week (a starter with none is on bye: 0 points
and 0 projection throughout). Sort the distinct kickoffs; a kickoff starts a new slate when
it is more than 2 hours after the current slate's FIRST kickoff (4:05 + 4:25 are one slate,
1:00 and 4:05 are two, a Monday 7:15 + 8:15 double-header is one). A slate is named from its
first kickoff in America/New_York ("the early games", "Thursday night", ...).

Checkpoint 0 is "Before kickoff" (everyone at his projection). Checkpoint k is after slate k:
starters in slates 1..k count their actual points, the rest their projections. The last
checkpoint, after the last slate, is "Final": P is 1, 0 or 0.5 by the official result.

Output of ``build``: {"model": {"sd", "method"}, "weeks": [week, ...], "favorites": {"won", "lost"}}
with ``week`` = {"week", "checkpoints": [{"label", "slate"}, ...], "games": [game, ...],
"headlines": {"comeback", "collapse", "swing", "upset"}} and ``game`` = {"home", "away",
"p_home", "home_pts", "away_pts", "home_mu", "away_mu"} (+ "note"), each list holding one entry
per checkpoint. ``live`` returns the same pieces for the week in progress plus "pregame".
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

SKILL = ("QB", "RB", "WR", "TE")
# sd of a starter's miss, as [flat, per projected point]: sd = flat + per x projection.
SD = {**{pos: (3.0, 0.35) for pos in SKILL}, "K": (5.7, 0.0), "HC": (4.5, 0.0), "other": (3.0, 0.0)}
SLATE_GAP_MS = 2 * 3600 * 1000     # a kickoff this long after a slate's first one starts a new slate
BANK_TOL = 0.05                    # starters' points vs the official score before we add a note
P_EDGE = 0.0001                    # an uncertain game never shows as exactly 0% or 100%
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

METHOD = ("Each starter still to play counts as his ESPN projection, give or take a typical miss, sized "
          "from this league's first four weeks: 3 points plus 35% of the projection for QB, RB, WR and TE; "
          "5.7 for kickers; 4.5 for head coaches; 3 for everyone else. Points already scored are banked. "
          "A team's chance comes from the gap between the two projected scores against their combined spread. "
          "Lineups are the ones each team ended up starting.")


# ── the model ──────────────────────────────────────────────────────────────────
def sd_of(pos: str, proj: float) -> float:
    """Typical miss of one starter's score against his ESPN projection."""
    if not proj:
        return 0.0  # projected exactly 0: out, or no game
    flat, per = SD.get(pos) or SD["other"]
    return flat + per * max(proj, 0.0)


def phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def win_prob(mu_a: float, var_a: float, mu_b: float, var_b: float) -> float:
    """Chance team A outscores team B; 1, 0 or 0.5 by the sign when neither has any spread."""
    var = var_a + var_b
    gap = mu_a - mu_b
    if var <= 0:
        return 0.5 if abs(gap) < 1e-9 else 1.0 if gap > 0 else 0.0
    return phi(gap / math.sqrt(var))


# ── slates ─────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _eastern() -> ZoneInfo:
    return ZoneInfo("America/New_York")  # looked up on first use so a missing tz database can't break import


def slate_label(first_ms: int) -> str:
    """Name a slate from its first kickoff (epoch ms), in New York time."""
    dt = datetime.fromtimestamp(first_ms / 1000, tz=_eastern())
    day = WEEKDAYS[dt.weekday()]
    if day == "Sunday":
        if dt.hour < 12:
            return "the Sunday morning game"
        if dt.hour < 16:
            return "the early games"
        if dt.hour < 19:
            return "the late games"
        return "Sunday night"
    return f"{day} night" if dt.hour >= 19 else f"{day} afternoon"


def slate_starts(kicks: Iterable[int]) -> list[int]:
    """First kickoff (epoch ms) of each slate, in order."""
    firsts: list[int] = []
    for k in sorted(set(kicks)):
        if not firsts or k - firsts[-1] > SLATE_GAP_MS:
            firsts.append(k)
    return firsts


def slate_names(firsts: list[int]) -> list[str]:
    """One name per slate. Two slates that would share a name (Thanksgiving has two Thursday
    afternoon games) get their kickoff time added, so every checkpoint reads differently."""
    names = [slate_label(f) for f in firsts]
    out = []
    for f, name in zip(firsts, names, strict=True):
        if names.count(name) > 1:
            dt = datetime.fromtimestamp(f / 1000, tz=_eastern())
            name = f"{name} ({dt.hour % 12 or 12}:{dt.minute:02d} ET)"
        out.append(name)
    return out


def slate_of(firsts: list[int], kick: int | None) -> int | None:
    """Index of the slate a kickoff belongs to; None for a starter with no game."""
    if kick is None or not firsts:
        return None
    return max(bisect_right(firsts, kick) - 1, 0)


# ── win chance across a week's checkpoints ─────────────────────────────────────
@dataclass(frozen=True)
class Starter:
    pos: str
    proj: float          # ESPN's pregame projection
    pts: float           # points actually scored
    slate: int | None    # index of the slate his game is in; None = no game (bye), nothing to count


def _curve(starters: list[Starter], upto: int, final: float | None) -> tuple[list, list, list]:
    """Banked points, mean score and variance at checkpoints 0..upto. Checkpoint k banks the
    starters in slates 0..k-1; ``final`` (the official score) replaces the last checkpoint."""
    bank, mu, var = [], [], []
    for k in range(upto + 1):
        b = m = v = 0.0
        for s in starters:
            if s.slate is None:
                continue
            if s.slate < k:
                b += s.pts
            else:
                m += s.proj
                v += sd_of(s.pos, s.proj) ** 2
        bank.append(b)
        mu.append(b + m)
        var.append(v)
    if final is not None:
        bank[-1] = mu[-1] = final
        var[-1] = 0.0
    return bank, mu, var


def _chance(mu_a: float, var_a: float, mu_b: float, var_b: float) -> float:
    p = win_prob(mu_a, var_a, mu_b, var_b)
    if var_a + var_b > 0:
        p = min(max(p, P_EDGE), 1 - P_EDGE)  # only a finished game is 0% or 100%
    return round(p, 4)


def _game(home: int, away: int, hs: list[Starter], as_: list[Starter], upto: int,
          official: tuple[float, float] | None) -> dict:
    """One matchup's win chance at every checkpoint 0..upto. ``official`` = the final score when
    the last checkpoint is Final; if the starters' points don't add up to it, a note says so."""
    fh, fa = (round(official[0], 2), round(official[1], 2)) if official else (None, None)
    hb, hm, hv = _curve(hs, upto, fh)
    ab, am, av = _curve(as_, upto, fa)
    game = {"home": home, "away": away,
            "p_home": [_chance(hm[k], hv[k], am[k], av[k]) for k in range(upto + 1)],
            "home_pts": [round(x, 2) for x in hb], "away_pts": [round(x, 2) for x in ab],
            "home_mu": [round(x, 2) for x in hm], "away_mu": [round(x, 2) for x in am]}
    if official:
        th, ta = sum(s.pts for s in hs), sum(s.pts for s in as_)
        if abs(th - fh) > BANK_TOL or abs(ta - fa) > BANK_TOL:
            game["note"] = (f"The starters' points add up to {th:.1f} and {ta:.1f}, but ESPN's scores are "
                            f"{fh:.1f} and {fa:.1f}, so the odds before Final are rough.")
    return game


def _view(game: dict, side: str) -> tuple[int, int, list[float], float, float]:
    """(team, opponent, that team's win chances, its score, the opponent's score) at the last checkpoint."""
    home = side == "home"
    p = game["p_home"] if home else [round(1 - x, 4) for x in game["p_home"]]
    mine, theirs = ("home_pts", "away_pts") if home else ("away_pts", "home_pts")
    return (game["home"] if home else game["away"], game["away"] if home else game["home"],
            p, game[mine][-1], game[theirs][-1])


def _swing(games: list[dict]) -> dict | None:
    """Biggest move in win chance between two consecutive checkpoints, for the team that gained."""
    best = None
    for gi, g in enumerate(games):
        for k in range(1, len(g["p_home"])):
            move = g["p_home"][k] - g["p_home"][k - 1]
            if move and (best is None or abs(move) > best[0] + 1e-9):
                best = (abs(move), gi, k, move)
    if best is None:
        return None
    _, gi, k, move = best
    team, opp, p, _, _ = _view(games[gi], "home" if move > 0 else "away")
    return {"team": team, "opp": opp, "from": p[k - 1], "to": p[k], "at": k}


def _headlines(games: list[dict]) -> dict:
    """The week's talking points, from finished games (see the module docstring)."""
    comeback = collapse = upset = None
    for g in games:
        hs, as_ = g["home_pts"][-1], g["away_pts"][-1]
        if hs == as_:
            continue
        won = "home" if hs > as_ else "away"
        lost = "away" if won == "home" else "home"
        team, opp, p, score, opp_score = _view(g, won)
        before = p[:-1]
        low = min(before)
        if low < 0.5 and (comeback is None or low < comeback["low"]):
            comeback = {"team": team, "opp": opp, "low": low, "at": before.index(low),
                        "score": score, "opp_score": opp_score}
        team, opp, p, score, opp_score = _view(g, lost)
        high = max(p[:-1])
        if high > 0.5 and (collapse is None or high > collapse["high"]):
            collapse = {"team": team, "opp": opp, "high": high, "at": p[:-1].index(high),
                        "score": score, "opp_score": opp_score}
        pre = g["p_home"][0] if won == "home" else 1 - g["p_home"][0]
        if pre < 0.5 and (upset is None or pre < upset["pregame"]):
            team, opp, _, score, opp_score = _view(g, won)
            upset = {"team": team, "opp": opp, "pregame": round(pre, 4), "score": score,
                     "opp_score": opp_score}
    return {"comeback": comeback, "collapse": collapse, "swing": _swing(games), "upset": upset}


# ── completed weeks → the Sunday recap ─────────────────────────────────────────
def _checkpoints(names: list[str], final: bool) -> list[dict]:
    """"Before kickoff", then one per slate banked so far. With ``final`` the last slate was the
    end of the week, so its checkpoint is "Final" (``slate`` still says which games closed it out)."""
    out = [{"label": "Before kickoff"}]
    for i, name in enumerate(names):
        out.append({"label": "Final" if final and i == len(names) - 1 else f"After {name}", "slate": name})
    return out


def _starters(rows: Iterable[tuple[str, float, float, int | None]], firsts: list[int]) -> list[Starter]:
    """rows: (position, projection, points, kickoff ms or None) for each starter. One with no kickoff
    is on bye (0 and 0, so nothing to count); if he somehow has a projection or points anyway, he
    resolves with the last slate rather than being dropped."""
    last = max(len(firsts) - 1, 0)
    out = []
    for pos, proj, pts, kick in rows:
        slate = slate_of(firsts, kick)
        if slate is None and (proj or pts):
            slate = last
        out.append(Starter(pos, proj, pts, slate))
    return out


def _has_projections(*sides: list[Starter]) -> bool:
    """False when ESPN gave a lineup no projections at all: odds from nothing would be made up."""
    return all(sum(s.proj for s in side) > 0 for side in sides)


def _week(ctx, w: int) -> dict | None:
    rosters = ctx.rosters.get(w, {})
    proj, pts, kick = ctx.proj.get(w, {}), ctx.pts.get(w, {}), ctx.kickoff.get(w, {})
    games_in = [m for m in ctx.matchups.get(w, []) if m["home"] in rosters and m["away"] in rosters]

    def rows(team: int):
        return [(ctx.pos.get(pid, "?"), float(proj.get(pid) or 0.0), float(pts.get(pid) or 0.0), kick.get(pid))
                for pid in sorted(rosters[team].started)]

    lineups = {t: rows(t) for m in games_in for t in (m["home"], m["away"])}
    firsts = slate_starts(k for r in lineups.values() for *_, k in r if k is not None)
    names = slate_names(firsts) or ["the games"]  # no kickoff times at all: one slate, the whole week
    games = []
    for m in games_in:
        hs, as_ = _starters(lineups[m["home"]], firsts), _starters(lineups[m["away"]], firsts)
        if _has_projections(hs, as_):
            games.append(_game(m["home"], m["away"], hs, as_, len(names),
                               (float(m["home_score"]), float(m["away_score"]))))
    if not games:
        return None
    return {"week": w, "checkpoints": _checkpoints(names, True), "games": games,
            "headlines": _headlines(games)}


def _favorites(weeks: list[dict]) -> dict:
    """Pregame favorites' record over every finished game (50/50 games and ties don't count)."""
    won = lost = 0
    for week in weeks:
        for g in week["games"]:
            pre, hs, as_ = g["p_home"][0], g["home_pts"][-1], g["away_pts"][-1]
            if pre == 0.5 or hs == as_:
                continue
            if (pre > 0.5) == (hs > as_):
                won += 1
            else:
                lost += 1
    return {"won": won, "lost": lost}


def build(ctx) -> dict | None:
    """The recap for every completed week (``window.LEAGUE_DATA.recap``), or None with no weeks."""
    weeks = [wk for w in ctx.weeks if (wk := _week(ctx, w))]
    if not weeks:
        return None
    return {"model": {"sd": {k: list(v) for k, v in SD.items()}, "method": METHOD},
            "weeks": weeks, "favorites": _favorites(weeks)}


# ── the week in progress → upset alert + this week's swings so far ─────────────
def _iso_ms(iso) -> int | None:
    """Epoch ms of an ISO-8601 kickoff from live.py; None when it has none."""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_eastern())
    return int(dt.timestamp() * 1000)


def _upset_watch(games: list[dict]) -> dict | None:
    """The pregame underdog with the best chance at the latest checkpoint, if it's now 50% or better."""
    best = None
    for g in games:
        pre = g["p_home"][0]
        if pre == 0.5:
            continue
        side = "home" if pre < 0.5 else "away"
        team, opp, p, _, _ = _view(g, side)
        if p[-1] >= 0.5 and (best is None or (p[-1], -p[0]) > (best["now"], -best["pregame"])):
            best = {"team": team, "opp": opp, "pregame": p[0], "now": p[-1], "at": len(p) - 1}
    return best


def live(live_data: dict) -> dict | None:
    """Odds for the week in progress (``LIVE_DATA.winprob``): the pregame odds of every matchup, and
    how each one moved as slates of games finished. A slate is finished when every starter in it is
    "final"; points of games still live or to come are partial, so they are never banked."""
    matchups = live_data.get("matchups") or []
    if not matchups:
        return None
    lineups = []
    for m in matchups:
        sides = []
        for side in (m["home"], m["away"]):
            sides.append([(p.get("pos") or "?", float(p.get("projected") or 0.0), float(p.get("points") or 0.0),
                           _iso_ms(p.get("kickoff")), p.get("status")) for p in side.get("starters") or []])
        lineups.append(sides)
    firsts = slate_starts(k for sides in lineups for rows in sides for _, _, _, k, _ in rows if k is not None)
    names = slate_names(firsts)

    # How many slates, from the first, are completely final.
    open_slates = {slate_of(firsts, k) for sides in lineups for rows in sides
                   for _, _, _, k, status in rows if k is not None and status != "final"}
    done_n = next((i for i in range(len(firsts)) if i in open_slates), len(firsts))
    done = bool(firsts) and done_n == len(firsts)

    pregame, games = [], []
    for m, (home_rows, away_rows) in zip(matchups, lineups, strict=True):
        hs = _starters([r[:4] for r in home_rows], firsts)
        as_ = _starters([r[:4] for r in away_rows], firsts)
        if not _has_projections(hs, as_):
            continue
        official = None
        if done:  # every starter is final, so ESPN's score is the result
            official = (float(m["home"].get("score") or 0.0), float(m["away"].get("score") or 0.0))
        g = _game(m["home"]["team"], m["away"]["team"], hs, as_, done_n if firsts else 0, official)
        pregame.append({"home": g["home"], "away": g["away"], "p_home": g["p_home"][0],
                        "proj_home": g["home_mu"][0], "proj_away": g["away_mu"][0]})
        if firsts:
            games.append(g)
    checkpoints = _checkpoints(names[:done_n], done) if firsts else []
    return {"week": live_data.get("week"), "pregame": pregame, "checkpoints": checkpoints, "games": games,
            "done": done, "headlines": {"swing": _swing(games), "upset_watch": _upset_watch(games)}}
