"""What-if lineups: every team's score with its best possible lineup each week, and the
matchups a better lineup would have flipped. Output: ``window.LEAGUE_DATA.whatif``.

The rule
    A team's *best lineup* for a week is the highest-scoring legal lineup (ESPN's own slot
    rules, so FLEX, IDP and head coach need no position tables) from the players it could
    actually have started: its box-score roster minus anyone it only picked up after his
    game kicked off (``ctx.startable``; whoever really started counts even if that guess
    says otherwise). ``best = max(score, best lineup)``, so a best
    lineup never reads lower than what the team really scored. If the best lineup is the
    lineup the team really started (no start/sit change would add a point), best is just
    the score: a few hundredths of ESPN rounding never count as an improvement.

    The opponent keeps its ACTUAL score. A *flip* is a game a team lost (its score was below
    the opponent's) that its best lineup would have won (best above the opponent's score).
    Exactly equal would have been a tie, not a win, so that isn't a flip. Only the loser of
    a game can flip it, so a game has at most one flipped side.

Records
    The *best record* is the record if this team had set its best lineup every week and
    every opponent had kept its actual score: a win when best beats the opponent's score,
    a tie when equal, a loss otherwise. A team that really won still wins (best is never
    below its score); a tie can turn into a win, which the best record counts but a flip
    doesn't (nobody lost). Records and ``points_left`` (best minus score, summed) cover the
    regular season only, like ESPN's standings. Games after it (``week > reg_weeks``) are
    still listed and still produce flips, but they carry ``"playoff": true``.

Swaps
    For each flip, ``swap_in`` is who was in the best lineup but not in the lineup that was
    started, ``swap_out`` who was started but isn't in the best lineup (both sorted by
    points, high to low). Where two players score the same, the one who really started is
    kept, so a swap doesn't trade a player for an equal scorer.

``build(ctx)`` returns ``{"weeks": [{"week", "games": [{"home", "away", "home_score",
"away_score", "home_best", "away_best", "flipped", "both_best_winner"}]}], "teams": [{"team",
"wins", "losses", "ties", "best_wins", "best_losses", "best_ties", "points_left", "flips":
[{"week", "opp", "score", "best", "opp_score", "swap_in", "swap_out"}]}], "flips_total"}``,
or None while no game has been played. ``flipped`` is the team id whose best lineup would
have won, ``both_best_winner`` the team that wins if BOTH set best lineups (None if dead even),
``flips_total`` the number of flipped games (playoff weeks included). Games and flips after
the regular season also carry ``"playoff": true``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from league.lineup import best_lineup


@dataclass
class _Side:
    """One team's side of a game: what it scored, its best lineup, and what would change."""
    team: int
    score: float
    best: float
    swap_in: list[dict] = field(default_factory=list)
    swap_out: list[dict] = field(default_factory=list)


def _r2(x) -> float:
    return round(float(x), 2)


def _startable(ctx, week: int, team: int, roster) -> set[str]:
    """Players who could have been started (``ReportContext.startable``). The whole roster
    when ctx can't tell."""
    fn = getattr(ctx, "startable", None)
    return set(fn(week, team)) if callable(fn) else set(roster.players)


def _player(ctx, week: int, roster, pid: str) -> dict:
    name = roster.players[pid][0] if pid in roster.players else ctx.names.get(pid, f"Player {pid}")
    pos = ctx.pos.get(pid) or (roster.players[pid][1] if pid in roster.players else "") or "?"
    return {"id": pid, "name": name, "pos": pos, "points": _r2(ctx.pts.get(week, {}).get(pid, 0.0))}


def _swap(ctx, week: int, roster, pids: set[str]) -> list[dict]:
    return sorted((_player(ctx, week, roster, p) for p in pids), key=lambda p: (-p["points"], p["id"]))


def _side(ctx, week: int, team: int, score: float) -> _Side:
    """``team``'s best lineup for ``week`` against the score it really had."""
    roster = ctx.rosters.get(week, {}).get(team)
    if roster is None:
        return _Side(team, score, score)
    started = set(roster.started)
    # Someone who really started could be started, whatever the late-add guess says. Ties between
    # equal scorers go to the real starter (the greedy fill keeps list order among equals).
    ids = sorted(_startable(ctx, week, team, roster) | started, key=lambda p: (p not in started, p))
    total, picked = best_lineup(ctx.pts.get(week, {}), ctx.lu.eligible, ids, ctx.lu.slots)
    total = _r2(total)
    if total <= score or picked == started:
        return _Side(team, score, score)
    return _Side(team, score, total, _swap(ctx, week, roster, picked - started),
                 _swap(ctx, week, roster, started - picked))


@dataclass
class _Tally:
    wins: int = 0
    losses: int = 0
    ties: int = 0
    best_wins: int = 0
    best_losses: int = 0
    best_ties: int = 0
    points_left: float = 0.0
    flips: list[dict] = field(default_factory=list)


def build(ctx) -> dict | None:
    reg = int(getattr(ctx, "reg_weeks", 0) or 0)
    weeks: list[dict] = []
    tally: dict[int, _Tally] = {}
    flips_total = 0
    for w in ctx.weeks:
        games = []
        for g in ctx.matchups.get(w, []):
            home, away = int(g["home"]), int(g["away"])
            hs, as_ = _r2(g["home_score"]), _r2(g["away_score"])
            sides = (_side(ctx, w, home, hs), _side(ctx, w, away, as_))
            playoff = bool(reg) and w > reg
            flipped = None
            for me, opp in (sides, sides[::-1]):
                t = tally.setdefault(me.team, _Tally())
                if me.score < opp.score and me.best > opp.score:
                    flipped = me.team
                    t.flips.append({"week": w, "opp": opp.team, "score": me.score, "best": me.best,
                                    "opp_score": opp.score, "swap_in": me.swap_in, "swap_out": me.swap_out,
                                    **({"playoff": True} if playoff else {})})
                if playoff:
                    continue
                t.points_left += me.best - me.score
                if me.score > opp.score:
                    t.wins += 1
                elif me.score < opp.score:
                    t.losses += 1
                else:
                    t.ties += 1
                if me.best > opp.score:
                    t.best_wins += 1
                elif me.best < opp.score:
                    t.best_losses += 1
                else:
                    t.best_ties += 1
            flips_total += flipped is not None
            hb, ab = sides[0].best, sides[1].best
            games.append({"home": home, "away": away, "home_score": hs, "away_score": as_,
                          "home_best": hb, "away_best": ab, "flipped": flipped,
                          "both_best_winner": home if hb > ab else away if ab > hb else None,
                          **({"playoff": True} if playoff else {})})
        if games:
            weeks.append({"week": w, "games": games})
    if not weeks:
        return None
    teams = [{"team": tid, "wins": t.wins, "losses": t.losses, "ties": t.ties,
              "best_wins": t.best_wins, "best_losses": t.best_losses, "best_ties": t.best_ties,
              "points_left": _r2(t.points_left), "flips": t.flips}
             for tid, t in sorted(tally.items())]
    return {"weeks": weeks, "teams": teams, "flips_total": flips_total}
