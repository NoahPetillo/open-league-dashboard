"""The race to avoid last place (last place does the punishment) and playoff odds.

Simulates the rest of the regular season many times. Each team's weekly score is
drawn from a normal distribution: its mean is the team's scoring average so far,
shrunk toward the league average (three weeks of data is noisy), and its spread is
the league-wide week-to-week spread. Games are played on ESPN's real schedule;
final standings sort by wins, then the league's tiebreakers (``tiebreak``, below).

From the simulations come each team's odds of finishing last, projected wins, the
league's "magic number" (the win total that's almost always safe) and each team's
odds of reaching it, what last place usually ends up with, and which games this
week swing the race most.

With ``playoff_teams`` (and the divisions) the same simulations also give playoff
odds, by ESPN's rules: in a league with divisions every division winner gets in and
takes the top seeds, and the remaining spots go to the best records. When the bracket
isn't a power of two, the top seeds get a first-round bye (6 teams: seeds 1 and 2).

Ties in the standings, for playoff spots and for last place alike, are broken by
``tiebreak``: the league's own seeding rule first (ESPN setting ``playoffSeedingRule``,
see ``tiebreak_order``), then the rest of ESPN's order: head-to-head record among the
tied teams (only when they've all played each other equally often), points for,
division record, points against, then a coin flip. Without ``tiebreak`` it's division
record, then points for.

``races`` gives the same picture for each race the Odds tab can show: ``last`` (finish
last), ``playoffs`` (make them) and ``bye`` (get one). Each has every team's odds, the
magic number (for last: the fewest wins that finish last ≤5% of the time; for the
other two: the fewest that get you in ≥95% of the time), what the cutoff team ends up
with (last place's wins; the fewest wins of any playoff team / bye team), and which of
next week's games swing it most.
"""

from __future__ import annotations

import random
import statistics
from collections import Counter, defaultdict

PRIOR_GAMES = 5       # weight of the league average in each team's scoring mean
MIN_SPREAD = 24.0     # weekly scores really swing ~25 pts; a few weeks of data understates it
SAFE_ODDS = 0.05      # magic number = fewest wins that finish last ≤5% of the time
DEFAULT_SIMS = 10_000


def _score_model(scores: dict[int, list[float]]) -> tuple[dict[int, float], float]:
    every = [s for ss in scores.values() for s in ss]
    league_avg = statistics.fmean(every) if every else 100.0
    means = {t: (sum(ss) + PRIOR_GAMES * league_avg) / (len(ss) + PRIOR_GAMES)
             for t, ss in scores.items()}
    # Week-to-week spread around each team's own average, pooled across the league.
    resid = [s - statistics.fmean(ss) for ss in scores.values() if len(ss) > 1 for s in ss]
    spread = statistics.pstdev(resid) * 1.15 if len(resid) > 2 else 25.0  # small-sample bump
    return means, max(spread, MIN_SPREAD)


def _k(w: float) -> str:
    return str(int(w)) if float(w).is_integer() else str(w)


def byes_for(playoff_teams: int) -> int:
    """First-round byes in a single-elimination bracket: next power of two minus teams."""
    return (1 << (playoff_teams - 1).bit_length()) - playoff_teams if playoff_teams > 1 else 0


# ESPN's playoff seeding tiebreakers (what comes after winning percentage). A league picks
# the first one (scheduleSettings.playoffSeedingRule); the rest follow in ESPN's order.
TIEBREAK_KEYS = {"H2H_RECORD": "h2h", "TOTAL_POINTS_SCORED": "pf",
                 "INTRA_DIVISION_RECORD": "div", "TOTAL_POINTS_AGAINST": "pa"}
ESPN_ORDER = ("h2h", "pf", "div", "pa")
TIEBREAK_WORDS = {"h2h": "head-to-head record", "pf": "points for", "div": "division record",
                  "pa": "points against"}


def tiebreak_order(rule: str | None) -> tuple[str, ...] | None:
    """The tiebreakers for ESPN seeding rule ``rule``, in order; None if it isn't one we know."""
    first = TIEBREAK_KEYS.get(rule or "")
    return (first, *[k for k in ESPN_ORDER if k != first]) if first else None


class Standings:
    """One finished (or simulated) season's numbers that ties are broken on."""

    def __init__(self, wins: dict, pf: dict, pa: dict, div_wins: dict, beat: dict, met: dict,
                 played: list[tuple[int, int]] = ()):
        self.wins, self.pf, self.pa, self.div_wins = wins, pf, pa, div_wins
        self.beat, self.met = beat, met   # (team, opp) → wins over / games against that opponent
        self.played = played              # more games on top of those: (winner, loser)
        self._keys, self._key, self._n = None, {}, 0

    def _value(self, key: str, group: list[int]) -> dict | None:
        """Each tied team's number for tiebreaker ``key`` (higher is better), or None when
        the tiebreaker can't separate this group (head-to-head with uneven meetings)."""
        if key == "pf":
            return self.pf
        if key == "pa":  # ESPN gives this one to the team with more points against
            return self.pa
        if key == "div":
            return self.div_wins
        inside = set(group)
        games = {(a, b): self.met.get((a, b), 0) for a in group for b in group if a != b}
        won = {t: sum(self.beat.get((t, o), 0) for o in group if o != t) for t in group}
        for w, lose in self.played:
            if w in inside and lose in inside:
                games[(w, lose)] += 1
                games[(lose, w)] += 1
                won[w] += 1
        if not games or len(set(games.values())) != 1 or not next(iter(games.values())):
            return None
        return won

    def rank(self, teams, keys: tuple[str, ...], rng: random.Random) -> list[int]:
        """``teams`` best first: by wins, then each of ``keys`` among teams still tied
        (re-asked within each smaller tie), then a coin flip."""
        def split(group: list[int], keys: tuple[str, ...]) -> list[int]:
            if len(group) < 2:
                return group
            if not keys:
                group = list(group)
                rng.shuffle(group)
                return group
            val = self._value(keys[0], group)
            if val is None:
                return split(group, keys[1:])
            out = []
            for v in sorted({val[t] for t in group}, reverse=True):
                out += split([t for t in group if val[t] == v], keys[1:])
            return out

        # Wins and the plain-number tiebreakers before any head-to-head sort in one go; only
        # teams still level on all of them go through split().
        if self._keys != keys:  # the same season gets ranked several times (divisions, field, table)
            self._n = keys.index("h2h") if "h2h" in keys else len(keys)
            cols = [self._value(k, []) for k in keys[:self._n]]
            self._key = {t: (w, *(c[t] for c in cols)) for t, w in self.wins.items()}
            self._keys = keys
        key, later = self._key, keys[self._n:]
        ordered = sorted(teams, key=key.__getitem__, reverse=True)
        out, i, size = [], 0, len(ordered)
        while i < size:
            j = i + 1
            while j < size and key[ordered[j]] == key[ordered[i]]:
                j += 1
            if j - i == 1:
                out.append(ordered[i])
            else:
                out += split(ordered[i:j], later)
            i = j
        return out


def playoff_field(ids: list[int], groups: list[list[int]], wins: dict, pf: dict, div_wins: dict,
                  spots: int, rank=None) -> tuple[list[int], list[int]]:
    """``(seeds, division_winners)`` for one set of final standings.

    Seeds run best first: division winners, then the best remaining records until
    ``spots`` teams are in. ``rank(teams)`` orders teams best first; without it every
    comparison is wins, then division wins, then points for."""
    if rank is None:
        key = lambda t: (wins[t], div_wins[t], pf[t])  # noqa: E731
        rank = lambda ts: sorted(ts, key=key, reverse=True)  # noqa: E731
    winners = rank([rank(g)[0] for g in groups if g])[:spots]
    taken = set(winners)
    rest = rank([t for t in ids if t not in taken])
    return winners + rest[:max(0, spots - len(winners))], winners


def simulate(teams: list[dict], schedule: dict[int, list[tuple[int, int]]], weeks_left: list[int],
             sims: int = DEFAULT_SIMS, seed: int = 7, playoff_teams: int = 0,
             divisions: dict[int, int] | None = None, tiebreak: tuple[str, ...] | None = None) -> dict:
    """``teams``: [{id, wins, losses, ties, points_for, scores, div_wins?, points_against?,
    beat?, met?}] — current state (``beat``/``met``: opponent → wins over / games against).
    ``tiebreak``: the league's tiebreakers in order (``tiebreak_order``).
    ``schedule``: week → [(team_a, team_b), ...] for the unplayed weeks.
    ``playoff_teams`` > 0 adds p_playoffs / p_division / p_bye per team (``divisions``:
    team id → division id; a game between teammates of a division counts as a division
    game). With no weeks left the answer is already decided, so one pass is enough."""
    rng = random.Random(seed)
    if not weeks_left:
        sims = 1  # season over: nothing is random any more
    ids = [t["id"] for t in teams]
    base_w = {t["id"]: t["wins"] + 0.5 * t.get("ties", 0) for t in teams}
    base_pf = {t["id"]: t["points_for"] for t in teams}
    base_dw = {t["id"]: t.get("div_wins", 0) for t in teams}
    base_pa = {t["id"]: t.get("points_against", 0.0) for t in teams}
    base_beat = {(t["id"], o): n for t in teams for o, n in (t.get("beat") or {}).items()}
    base_met = {(t["id"], o): n for t in teams for o, n in (t.get("met") or {}).items()}
    # Head-to-head only decides anything if it comes before the point totals (scores almost
    # never tie), so only then is it worth tracking game by game.
    keys = tiebreak or ()
    track_h2h = "h2h" in keys[:min((keys.index(k) for k in ("pf", "pa") if k in keys), default=len(keys))]
    groups: list[list[int]] = []             # the divisions, as lists of team ids
    if playoff_teams > 0 and divisions:
        for d in sorted({divisions[i] for i in ids if i in divisions}):
            groups.append([i for i in ids if divisions.get(i) == d])
    byes = byes_for(playoff_teams)
    same_div = {(a, b) for g in groups for a in g for b in g if a != b}
    means, spread = _score_model({t["id"]: t["scores"] for t in teams})

    last = Counter()
    final_wins = defaultdict(Counter)        # team → final wins → count
    last_given_wins = defaultdict(Counter)   # team → final wins → times finished last
    last_place_wins = Counter()              # final wins of whoever finished last
    next_week = weeks_left[0] if weeks_left else None
    # Next week's games: team → (won that game?, finished last?) counts.
    swing = defaultdict(lambda: Counter())
    made, won_div, got_bye = Counter(), Counter(), Counter()   # playoff odds counts
    # Per race (last / playoffs / bye): team → final wins → times it happened; the cutoff
    # team's final wins; and next week's (won that game?, it happened?) counts.
    hit_given_wins = {k: defaultdict(Counter) for k in ("playoffs", "bye")}
    cutoff = {k: Counter() for k in ("playoffs", "bye")}
    swing_of = {k: defaultdict(Counter) for k in ("playoffs", "bye")}

    for _ in range(sims):
        wins, pf, dw, pa = dict(base_w), dict(base_pf), dict(base_dw), dict(base_pa)
        played = []                          # this run's games, for head-to-head
        won_next = {}
        for w in weeks_left:
            for a, b in schedule.get(w, []):
                sa, sb = rng.gauss(means[a], spread), rng.gauss(means[b], spread)
                pf[a] += sa
                pf[b] += sb
                pa[a] += sb
                pa[b] += sa
                winner = a if sa > sb else b
                wins[winner] += 1
                if (a, b) in same_div:
                    dw[winner] += 1
                if track_h2h:
                    played.append((winner, b if winner == a else a))
                if w == next_week:
                    won_next[a], won_next[b] = winner == a, winner == b
        if tiebreak:
            book = Standings(wins, pf, pa, dw, base_beat, base_met, played)
            rank = lambda ts, book=book: book.rank(ts, tiebreak, rng)  # noqa: E731
            order = rank(ids)
        else:
            rank = None
            order = sorted(ids, key=lambda t: (wins[t], dw[t], pf[t]), reverse=True)
        if playoff_teams > 0:
            seeds, champs = playoff_field(ids, groups, wins, pf, dw, playoff_teams, rank)
            made.update(seeds)
            won_div.update(champs)
            got_bye.update(seeds[:byes])
            for key, field in (("playoffs", seeds), ("bye", seeds[:byes])):
                if not field:
                    continue
                cutoff[key][min(wins[t] for t in field)] += 1
                inside = set(field)
                for t in ids:
                    hit_given_wins[key][t][wins[t]] += t in inside
                    if t in won_next:
                        swing_of[key][t][(won_next[t], t in inside)] += 1
        loser = order[-1]
        last[loser] += 1
        last_place_wins[wins[loser]] += 1
        for t in ids:
            final_wins[t][wins[t]] += 1
            last_given_wins[t][wins[t]] += t == loser
            if t in won_next:
                swing[t][(won_next[t], t == loser)] += 1

    def p_if(sw, t, won: bool) -> float | None:
        n = sw[t][(won, True)] + sw[t][(won, False)]
        return round(sw[t][(won, True)] / n, 4) if n else None

    p_last_if = lambda t, won: p_if(swing, t, won)  # noqa: E731

    pooled = Counter()
    for t in ids:
        pooled.update(final_wins[t])

    def magic_for(given: dict, good: bool) -> float | None:
        """Fewest final wins (seen in ≥1% of sims) where the event happens ≥95% of the time
        (good: playoffs, bye) or ≤5% of the time (last place). Pooled over every team."""
        hits = Counter()
        for t in ids:
            hits.update(given[t])
        for w in sorted(pooled):
            if pooled[w] < sims * 0.01:
                continue
            rate = hits[w] / pooled[w]
            if (rate >= 1 - SAFE_ODDS) if good else (rate <= SAFE_ODDS):
                return w
        return None

    # Magic number: fewest final wins that finish last ≤ SAFE_ODDS of the time (any team).
    magic = magic_for(last_given_wins, good=False)

    out_teams = []
    for t in teams:
        tid = t["id"]
        dist = final_wins[tid]
        opps = [b if a == tid else a for wk in weeks_left for a, b in schedule.get(wk, [])
                if tid in (a, b)]
        out_teams.append({
            "id": tid,
            "p_last": round(last[tid] / sims, 4),
            "exp_wins": round(sum(w * c for w, c in dist.items()) / sims, 2),
            "wins_dist": {_k(w): round(c / sims, 4) for w, c in sorted(dist.items())},
            "need": None if magic is None else max(0, int(magic - base_w[tid] + 0.999)),
            "p_reach_magic": None if magic is None else
                round(sum(c for w, c in dist.items() if w >= magic) / sims, 4),
            "games_left": len(opps),
            "score_mean": round(means[tid], 1),
            "sos": round(statistics.fmean(means[o] for o in opps), 1) if opps else None,
            "next_if_win": p_last_if(tid, True),
            "next_if_loss": p_last_if(tid, False),
        })
        if playoff_teams > 0:
            out_teams[-1].update({
                "p_playoffs": round(made[tid] / sims, 4),
                "p_division": round(won_div[tid] / sims, 4) if groups else None,
                "p_bye": round(got_bye[tid] / sims, 4) if byes else None,
            })

    games = []
    for a, b in schedule.get(next_week, []) if next_week else []:
        ta, tb = (next(x for x in out_teams if x["id"] == i) for i in (a, b))
        lev = sum(abs((x["next_if_loss"] or 0) - (x["next_if_win"] or 0)) for x in (ta, tb))
        games.append({"week": next_week, "a": a, "b": b, "swing": round(lev, 4)})

    def race(p_of: dict, given: dict, cut: Counter, sw: dict, good: bool) -> dict:
        m = magic_for(given, good)
        rows = []
        for t in ids:
            dist = final_wins[t]
            rows.append({
                "id": t, "p": round(p_of[t] / sims, 4),
                "need": None if m is None else max(0, int(m - base_w[t] + 0.999)),
                "p_reach_magic": None if m is None else round(sum(c for w, c in dist.items() if w >= m) / sims, 4),
                "next_if_win": p_if(sw, t, True), "next_if_loss": p_if(sw, t, False),
            })
        by = {x["id"]: x for x in rows}
        gs = []
        for a, b in schedule.get(next_week, []) if next_week else []:
            lev = sum(abs((by[i]["next_if_loss"] or 0) - (by[i]["next_if_win"] or 0)) for i in (a, b))
            gs.append({"week": next_week, "a": a, "b": b, "swing": round(lev, 4)})
        return {"magic_number": m, "safe_odds": SAFE_ODDS, "teams": rows,
                "cutoff_wins": {_k(w): round(c / sims, 4) for w, c in sorted(cut.items())},
                "next_week_games": sorted(gs, key=lambda g: -g["swing"])}

    races = {"last": race(last, last_given_wins, last_place_wins, swing, good=False)}
    if playoff_teams > 0:
        races["playoffs"] = race(made, hit_given_wins["playoffs"], cutoff["playoffs"], swing_of["playoffs"], good=True)
        if byes:
            races["bye"] = race(got_bye, hit_given_wins["bye"], cutoff["bye"], swing_of["bye"], good=True)

    out = {
        "sims": sims, "weeks_left": weeks_left, "score_spread": round(spread, 1), "races": races,
        "magic_number": magic, "safe_odds": SAFE_ODDS,
        "teams": out_teams,
        "last_place_wins": {_k(w): round(c / sims, 4) for w, c in sorted(last_place_wins.items())},
        "next_week_games": sorted(games, key=lambda g: -g["swing"]),
    }
    if playoff_teams > 0:
        out.update({"playoff_spots": playoff_teams, "byes": byes})
    # The rules the standings were sorted by, for the page to explain.
    out["tiebreak"] = list(tiebreak) if tiebreak else ["div", "pf"]
    out["division_winners"] = len(groups) > 1
    return out
