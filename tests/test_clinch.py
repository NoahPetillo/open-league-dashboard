"""Clinching scenarios: the six exact statuses checked against a brute-force oracle that plays
out every possible set of results, plus this week's scenarios and the magic numbers."""

from __future__ import annotations

import itertools
import random
from collections import Counter
from types import SimpleNamespace

import pytest

from league import clinch
from league.punishment import playoff_field

KINDS = ("playoffs_in", "playoffs_out", "division_won", "division_out", "last_safe", "last_locked")


# ── the oracle ──────────────────────────────────────────────────────────────────
# Written without any of clinch.py's reasoning. It plays out EVERY way the remaining games can
# go, ranks the final wins with the league's real field rules (league.punishment.playoff_field),
# and quantifies over the outcomes directly. Final wins that tie are broken by an arbitrary
# order (stand-in for division record and points); for one team X, "pessimistic" puts X below
# everyone it ties with and "optimistic" above everyone.
def final_wins(teams, wins, games):
    """Every distinct vector of final wins (indexed like ``teams``) over all outcomes."""
    pos = {t: i for i, t in enumerate(teams)}
    vecs = {tuple(wins[t] for t in teams)}
    for a, b in games:
        ia, ib = pos[a], pos[b]
        nxt = set()
        for v in vecs:
            w = list(v)
            w[ia] += 1
            nxt.add(tuple(w))
            w[ia] -= 1
            w[ib] += 1
            nxt.add(tuple(w))
        vecs = nxt
    return vecs


def standing(teams, divisions, spots, wins, order):
    """(field, division winners, last place) for final ``wins`` with ties broken by ``order``
    (team -> rank number, higher = better). Uses the league's real ``playoff_field``."""
    groups = [[t for t in teams if divisions[t] == d] for d in sorted(set(divisions.values()))]
    zero = dict.fromkeys(teams, 0)
    field, winners = playoff_field(list(teams), groups, wins, order, zero, spots)
    last = min(teams, key=lambda t: (wins[t], 0, order[t]))
    return set(field), set(winners), last


def oracle(teams, divisions, spots, wins, games):
    teams = sorted(teams)
    out = {t: dict.fromkeys(KINDS, None) for t in teams}
    vecs = [dict(zip(teams, v, strict=True)) for v in final_wins(teams, wins, games)]
    for x in teams:
        others = [t for t in teams if t != x]
        pess = {t: i + 1 for i, t in enumerate(others)} | {x: -1}
        opt = {t: i + 1 for i, t in enumerate(others)} | {x: len(teams) + 1}
        in_all = out_all = won_all = out_div = safe = locked = True
        for fin in vecs:
            field, winners, last = standing(teams, divisions, spots, fin, pess)
            in_all &= x in field
            won_all &= x in winners
            safe &= last != x
            field, winners, last = standing(teams, divisions, spots, fin, opt)
            out_all &= x not in field
            out_div &= x not in winners
            locked &= last == x
        out[x] = {"playoffs_in": in_all, "playoffs_out": out_all, "division_won": won_all,
                  "division_out": out_div, "last_safe": safe, "last_locked": locked}
    return out


# ── random leagues ──────────────────────────────────────────────────────────────
def random_state(rng, n, n_div, rmax, kmax=12, byes=False):
    """A mid-season snapshot: ids, divisions, current wins (some ties = half wins) spread
    out so statuses actually trigger, and ``r`` more weeks of games."""
    ids = rng.sample(range(1, 3 * n + 1), n)
    order = ids[:]
    rng.shuffle(order)
    divisions = {t: i % n_div for i, t in enumerate(order)}
    games = []
    for _ in range(min(rmax, rng.choice([1, 1, 2, 2, 3]))):
        week = ids[:]
        rng.shuffle(week)
        if byes and rng.random() < 0.5:
            week = week[:-2]
        games += [(week[i], week[i + 1]) for i in range(0, len(week) - 1, 2)]
    k = rng.randint(2, kmax)
    wins = {}
    stair = rng.random() < 0.5            # evenly spread records (a clear best and worst) or random ones
    spread = ids[:]
    rng.shuffle(spread)
    for i, t in enumerate(spread):
        p = (i + rng.random() * 0.6) / n if stair else rng.random()
        w = min(k, sum(rng.random() < p for _ in range(k)) if not stair else round(k * p))
        ties = rng.choice([0, 0, 0, 1, 2]) if w < k else 0
        wins[t] = w + 0.5 * ties
    return ids, divisions, wins, games


SHAPES = [
    # (name, teams, divisions, playoff spots, max weeks left, seeds)
    ("6 teams / 2 divs / 3 spots", 6, 2, 3, 3, 120),
    ("8 teams / 2 divs / 4 spots", 8, 2, 4, 3, 40),
    ("6 teams / 3 divs / 4 spots", 6, 3, 4, 3, 80),
    ("6 teams / 1 div / 3 spots", 6, 1, 3, 3, 60),
    ("4 teams / 2 divs / 2 spots (no wildcards)", 4, 2, 2, 3, 60),
]


def check_against_oracle(shape, seeds, byes=False):
    _name, n, n_div, spots, rmax, _ = shape
    seen = Counter()
    for seed in seeds:
        ids, divisions, wins, games = random_state(random.Random(seed), n, n_div, rmax, byes=byes)
        want = oracle(ids, divisions, spots, wins, games)
        for fast in (True, False):
            got = clinch.statuses(ids, divisions, spots, wins, games, fast=fast)
            assert got == want, (shape[0], seed, fast, ids, divisions, wins, games)
        seen.update(k for t in ids for k, v in want[t].items() if v)
    return seen


@pytest.mark.parametrize("shape", SHAPES, ids=[s[0] for s in SHAPES])
def test_statuses_match_the_brute_force_oracle(shape):
    seen = check_against_oracle(shape, range(shape[5]))
    # The seeds have to exercise every status, not just come out all false.
    for kind in KINDS:
        assert seen[kind] >= 2, (kind, seen)


@pytest.mark.parametrize("shape", [s for s in SHAPES if s[1] <= 6], ids=[s[0] for s in SHAPES if s[1] <= 6])
def test_byes_match_the_oracle_too(shape):
    check_against_oracle(shape, range(20), byes=True)


# ── build(): this week's scenarios and the magic numbers ───────────────────────
def season(rng, n=6, n_div=2, spots=3, played=3, left=2):
    """A ReportContext stand-in: ``played`` weeks of results and ``left`` weeks to go, every
    team playing every week (round-robin pairings, shuffled)."""
    ids = list(range(1, n + 1))
    divisions = {t: (t - 1) % n_div for t in ids}
    schedule, matchups = {}, {}
    for w in range(1, played + left + 1):
        week = ids[:]
        rng.shuffle(week)
        schedule[w] = [(week[i], week[i + 1]) for i in range(0, n, 2)]
        if w <= played:
            matchups[w] = [{"home": a, "away": b, "home_score": 100.0 + rng.random(), "away_score": 100.0 + rng.random()}
                           for a, b in schedule[w]]
    return SimpleNamespace(teams=[{"id": t} for t in ids], reg_weeks=played + left, playoff_teams=spots,
                           through=played, matchups=matchups, schedule=schedule, divisions=divisions)


def record(ctx):
    wins = dict.fromkeys(ctx.divisions, 0)
    for games in ctx.matchups.values():
        for g in games:
            wins[g["home"] if g["home_score"] > g["away_score"] else g["away"]] += 1
    return wins


def completions(way, games):
    """Every full result of ``games`` (0 = first team wins) that agrees with ``way``."""
    fixed = {(w["winner"], w["loser"]) for w in way}
    out = set()
    for result in itertools.product((0, 1), repeat=len(games)):
        if all(((b, a) if r else (a, b)) in fixed or ((a, b) if r else (b, a)) not in fixed
               for (a, b), r in zip(games, result, strict=True)):
            out.add(result)
    return out


@pytest.mark.parametrize("seed", range(25))
def test_scenarios_are_exactly_the_results_that_settle_it(seed):
    ctx = season(random.Random(seed), played=random.Random(seed).choice([2, 3, 4]))
    got = clinch.build(ctx)
    wins = record(ctx)
    this = ctx.schedule[ctx.through + 1]
    later = [g for w in range(ctx.through + 2, ctx.reg_weeks + 1) for g in ctx.schedule[w]]
    now = oracle(list(wins), ctx.divisions, ctx.playoff_teams, wins, this + later)
    outcome = {}
    for result in itertools.product((0, 1), repeat=len(this)):
        after = dict(wins)
        for (a, b), r in zip(this, result, strict=True):
            after[b if r else a] += 1
        outcome[result] = oracle(list(after), ctx.divisions, ctx.playoff_teams, after, later)
    listed = {(s["team"], s["kind"]): s["ways"] for s in got["scenarios"]}
    for t in wins:
        assert got["teams"][t - 1]["status"] == now[t]
        for kind in KINDS:
            want = {r for r, o in outcome.items() if o[t][kind]} if not now[t][kind] else set()
            ways = listed.get((t, kind), [])
            covered = set().union(*(completions(w, this) for w in ways)) if ways else set()
            assert covered == want, (seed, t, kind)
            for way in ways:  # minimal: dropping any one condition stops it being sure
                for i in range(len(way)):
                    assert not completions(way[:i] + way[i + 1:], this) <= want, (seed, t, kind, way)


@pytest.mark.parametrize("seed", range(25))
def test_magic_numbers_match_brute_force(seed):
    rng = random.Random(100 + seed)
    ctx = season(rng, played=rng.choice([1, 2, 3]), left=2)
    got = {r["team"]: r["magic"] for r in clinch.build(ctx)["teams"]}
    wins = record(ctx)
    left = [g for w in range(ctx.through + 1, ctx.reg_weeks + 1) for g in ctx.schedule[w]]
    ids = list(wins)
    for x in ids:
        mine = [g for g in left if x in g]
        rest = [g for g in left if x not in g]
        for kind, key in (("playoffs_in", "playoffs"), ("last_safe", "safe")):
            want = None
            for k in range(len(mine) + 1):
                sure = True
                for won in itertools.combinations(range(len(mine)), k):
                    after = dict(wins)
                    after[x] += k
                    for i, (a, b) in enumerate(mine):
                        if i not in won:
                            after[b if a == x else a] += 1
                    if not oracle(ids, ctx.divisions, ctx.playoff_teams, after, rest)[x][kind]:
                        sure = False
                        break
                if sure:
                    want = k
                    break
            assert got[x][key] == want, (seed, x, kind, got[x], want)


def test_nothing_to_decide_once_the_season_is_over():
    ctx = season(random.Random(3), played=3, left=0)
    got = clinch.build(ctx)
    assert got["week"] is None and got["scenarios"] == [] and got["weeks_left"] == 0
    for row in got["teams"]:  # only a tie in the final standings (tiebreakers) leaves one open
        s = row["status"]
        assert not (s["playoffs_in"] and s["playoffs_out"]) and not (s["last_safe"] and s["last_locked"])
        assert row["magic"]["playoffs"] in (0, None) and row["magic"]["safe"] in (0, None)
