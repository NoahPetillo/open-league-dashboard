"""Clinching scenarios: what each team has locked up or lost for good (exactly, never
simulated), and what this week's results could settle. Output: ``window.LEAGUE_DATA.clinch``.

The six statuses (``KINDS``), each a yes/no that holds however every remaining game goes:

    playoffs_in    in the playoff field          playoffs_out   out of the playoff field
    division_won   won the division              division_out   can't win the division
    last_safe      can't finish last             last_locked    will finish last (the punishment)

The field is the league's (``punishment.playoff_field``): division winners first, then the best
records. Ties in the final standings are always read against the team in question (a clinch
holds whoever wins every tiebreaker; an elimination holds even if the team won them all), so
nothing here depends on division records or points. Games are won or lost: with scores to two
decimals a tie basically never happens, and the page says the scenarios assume none.

``Board`` answers each status exactly (flows over the remaining schedule, checked against a
brute-force oracle in the tests). On top of it ``build(ctx)`` returns::

    {"week": the next week to play (None once the regular season is over), "weeks_left",
     "spots", "teams": [{"team", "wins", "losses", "ties", "status": {kind: bool},
                         "magic": {"playoffs": n | None, "safe": n | None}}],
     "scenarios": [{"team", "kind", "ways": [[{"winner", "loser"}, ...], ...]}]}

``magic`` is the fewest more wins that settle it with no help: win any ``n`` of the remaining
games (whichever ones, whatever everyone else does) and the team is in the playoffs / safe
from last. None when even winning out doesn't guarantee it, 0 when it's already settled.

``scenarios`` covers ``week``: for every team and every status it doesn't have yet, each way
this week's results settle it for sure. A way is a set of games that must go a certain way
(the other games can go either way); the list is every minimal way, fewest games first, so
together they are exactly the outcomes that settle it.
"""

from __future__ import annotations

from itertools import combinations, product

from league.odds import _standings

KINDS = ("playoffs_in", "playoffs_out", "division_won", "division_out", "last_safe", "last_locked")


def _orient_ok(need: dict[int, int], pair: list[list[int]], n: int) -> bool:
    """Can every game (``pair[i][j]`` games between teams i and j) be given to one of its two
    teams so that each team t in ``need`` gets at least ``need[t]`` of them?

    This is a max-flow (source -> game -> its two teams -> sink, one unit per game) solved by
    augmenting paths: start from a greedy assignment, then for every team still short, look for
    a chain of games it can take from a team that has a spare one. If no chain exists the
    teams reached form a group that needs more games than it plays: infeasible, exactly."""
    want = [0] * n
    for t, k in need.items():
        want[t] = k
    teams = [t for t in need if want[t] > 0]
    if not teams:
        return True
    won = [[0] * n for _ in range(n)]      # won[a][b]: games between a and b that a takes
    wins = [0] * n
    for a in teams:                         # greedy: a game goes to whoever is further behind
        row = pair[a]
        for b in range(n):
            p = row[b]
            if not p or (want[b] and b < a):
                continue
            for _ in range(p):
                if want[b] and want[b] - wins[b] > want[a] - wins[a]:
                    won[b][a] += 1
                    wins[b] += 1
                else:
                    won[a][b] += 1
                    wins[a] += 1
    for a in teams:
        while wins[a] < want[a]:
            prev = {a: -1}
            queue = [a]
            end = -1
            for u in queue:
                for v in range(n):
                    if won[v][u] and v not in prev:
                        prev[v] = u
                        if wins[v] > want[v]:
                            end = v
                            break
                        queue.append(v)
                if end >= 0:
                    break
            if end < 0:
                return False
            cur = end
            while cur != a:                 # hand one game back along the chain
                p = prev[cur]
                won[cur][p] -= 1
                won[p][cur] += 1
                cur = p
            wins[a] += 1
            wins[end] -= 1
    return True


class Board:
    """The games still to play as a graph over the teams, plus the league's structure
    (divisions and how many playoff spots there are). ``w2`` below is every team's wins
    counted in halves (a tie is half a win), indexed like ``ids``.

    Each ``Board.<status>(x, w2)`` answers one yes/no question about team index ``x``; all
    six are exact. ``fast=False`` turns off the cheap shortcuts (every doubtful case goes
    through the full search), which the tests use to cross-check the shortcuts."""

    def __init__(self, ids: list[int], division_of: dict[int, int], spots: int,
                 games: list[tuple[int, int]], fast: bool = True):
        self.ids = list(ids)
        n = self.n = len(self.ids)
        index = {t: i for i, t in enumerate(self.ids)}
        divs = sorted({division_of.get(t, 0) for t in self.ids})
        where = {d: i for i, d in enumerate(divs)}
        self.div = [where[division_of.get(t, 0)] for t in self.ids]
        self.nd = len(divs)
        self.members = [[i for i in range(n) if self.div[i] == d] for d in range(self.nd)]
        self.mates = [[m for m in self.members[self.div[i]] if m != i] for i in range(n)]
        # Wildcard spots: what's left after every division winner. No playoff statuses when
        # there's no bracket, when everyone makes it, or when winners alone overfill it.
        self.spots = spots
        self.wild = spots - self.nd if 0 < spots < n and spots >= self.nd else None
        self.fast = fast
        pair = [[0] * n for _ in range(n)]
        for a, b in games:
            if a in index and b in index and a != b:
                pair[index[a]][index[b]] += 1
                pair[index[b]][index[a]] += 1
        self.pair = pair
        self.deg = [sum(row) for row in pair]
        self._without: dict[int, tuple[list[list[int]], list[int]]] = {}

    # ── pieces shared by the checks ─────────────────────────────────────────────
    def _rest(self, x: int) -> tuple[list[list[int]], list[int]]:
        """The games that don't involve ``x``: pair counts and each team's number of them."""
        got = self._without.get(x)
        if got is None:
            pair = [row[:] for row in self.pair]
            for k in range(self.n):
                pair[x][k] = pair[k][x] = 0
            got = self._without[x] = (pair, [sum(row) for row in pair])
        return got

    def _needs_if_x_loses_out(self, x: int, w2: list[int]) -> list[int]:
        """Wins each other team still needs from games not involving ``x`` to reach ``x``'s
        final total when ``x`` loses everything left (and so hands each opponent a win)."""
        px, top = self.pair[x], w2[x]
        need = [0] * self.n
        for t in range(self.n):
            gap = top - w2[t] - 2 * px[t]
            if t != x and gap > 0:
                need[t] = (gap + 1) // 2
        return need

    def _search(self, cand: list[int], need: list[int], degp: list[int], pairp: list[list[int]],
                count: list[int], goal) -> bool:
        """Is there a set of ``cand`` teams that can all get ``need`` wins out of the games
        in ``pairp`` at once, such that ``goal`` holds for the per-division head count
        (``count`` already holds the free members)? ``goal`` only gets easier as counts grow.

        A set can all get what they need exactly when no group U of them needs more wins than
        there are games with one of its teams in them (Hall / max-flow min-cut), so the
        search adds one team at a time and checks only the new groups, dropping any branch
        that breaks a group."""
        div, nd = self.div, self.nd
        m = len(cand)
        tail = [[0] * nd for _ in range(m + 1)]
        for i in range(m - 1, -1, -1):
            tail[i] = tail[i + 1][:]
            tail[i][div[cand[i]]] += 1

        def rec(i: int, groups: list[tuple[tuple[int, ...], int]], have: list[int]) -> bool:
            if goal(have):
                return True
            if i == m or not goal([h + r for h, r in zip(have, tail[i], strict=True)]):
                return False
            t = cand[i]
            row, spare = pairp[t], degp[t] - need[t]
            grown = []
            for members, slack in groups:
                s = slack + spare - sum(row[u] for u in members)
                if s < 0:
                    break
                grown.append((members + (t,), s))
            else:
                have[div[t]] += 1
                hit = rec(i + 1, groups + grown, have)
                have[div[t]] -= 1
                if hit:
                    return True
            return rec(i + 1, groups, have)

        return rec(0, [((), 0)], list(count))

    # ── the six statuses ────────────────────────────────────────────────────────
    def division_won(self, x: int, w2: list[int]) -> bool:
        """Every mate, even winning all its games (including the one against ``x``), still
        finishes below ``x``'s total today. Strict: a tie could go either way."""
        deg = self.deg
        return all(w2[m] + 2 * deg[m] < w2[x] for m in self.mates[x])

    def last_locked(self, x: int, w2: list[int]) -> bool:
        """Even if ``x`` wins out, every other team's total today is still higher."""
        top = w2[x] + 2 * self.deg[x]
        return all(w2[t] > top for t in range(self.n) if t != x)

    def division_out(self, x: int, w2: list[int]) -> bool:
        """With ``x`` winning out, the mates can't all be held to ``x``'s total or less."""
        mates = self.mates[x]
        if not mates:
            return False
        pairp, degp = self._rest(x)
        top = w2[x] + 2 * self.deg[x]
        need = {}
        for m in mates:
            cap = (top - w2[m]) // 2              # wins m can take from the other games
            if cap < 0:
                return True
            if degp[m] > cap:
                need[m] = degp[m] - cap           # ...so it must lose at least this many
        return not _orient_ok(need, pairp, self.n)

    def last_safe(self, x: int, w2: list[int]) -> bool:
        """With ``x`` losing out, the other teams can't all reach ``x``'s total at once."""
        need = self._needs_if_x_loses_out(x, w2)
        pairp, degp = self._rest(x)
        if self.fast:
            total, easy = 0, True
            for t in range(self.n):
                if t == x:
                    continue
                if need[t] > degp[t]:
                    return True                   # one team can't even get there alone
                total += need[t]
                easy = easy and need[t] <= degp[t] // 2
            if total > sum(degp) // 2:
                return True                       # more wins needed than games left
            if easy:
                return False                      # an even split of every game does it
        return not _orient_ok({t: k for t, k in enumerate(need) if k > 0}, pairp, self.n)

    def playoffs_in(self, x: int, w2: list[int]) -> bool:
        """With ``x`` losing out, the other teams can't be arranged to push it out.

        ``x`` misses the field iff it isn't its division's winner and at least ``wild`` teams
        that aren't division winners finish ahead of it. If k teams of a division finish
        ahead (tied counts as ahead), one of them is that division's winner and k-1 are
        non-winners ahead of ``x``; in ``x``'s own division k must be at least 1."""
        wild = self.wild
        if wild is None:
            return False
        if self.fast and self.division_won(x, w2):
            return True                           # a division winner is always in
        need = self._needs_if_x_loses_out(x, w2)
        pairp, degp = self._rest(x)
        div, nd, dx = self.div, self.nd, self.div[x]

        def short(have: list[int]) -> bool:
            """True when these head counts leave ``x`` out of the field."""
            return have[dx] >= 1 and have[dx] - 1 + sum(
                max(0, c - 1) for d, c in enumerate(have) if d != dx) >= wild

        have = [0] * nd
        easy, hard = [], []
        for t in range(self.n):
            if t == x:
                continue
            if need[t] == 0:
                have[div[t]] += 1
            elif need[t] <= degp[t]:
                (easy if self.fast and need[t] <= degp[t] // 2 else hard).append(t)
        if self.fast:
            near = have[:]
            for t in easy:
                near[div[t]] += 1
            if short(near):
                return False                      # these all catch up together: split games evenly
            for t in hard:
                near[div[t]] += 1
            if not short(near):
                return True                       # not enough teams can catch up at all
        cand = sorted(easy + hard, key=lambda t: need[t])
        return not self._search(cand, need, degp, pairp, have, short)

    def playoffs_out(self, x: int, w2: list[int]) -> bool:
        """With ``x`` winning out, there's no way to still get in: not as division winner
        (see ``division_out``) and not as a wildcard, where ``x`` needs fewer than ``wild``
        non-winners ahead, i.e. at most ``wild - 1`` extra teams ahead of the first team
        in each division. The teams allowed ahead are chosen freely; the rest must be held
        to ``x``'s total or less (ties go to ``x``)."""
        wild = self.wild
        if wild is None:
            return False
        if not self.division_out(x, w2):
            return False
        if wild < 1:
            return True
        pairp, degp = self._rest(x)
        div, nd = self.div, self.nd
        top = w2[x] + 2 * self.deg[x]
        total = [0] * nd                          # teams other than x, per division
        held = [0] * nd                           # ...that can't beat x whatever happens
        need = [0] * self.n
        easy, hard = [], []
        for t in range(self.n):
            if t == x:
                continue
            total[div[t]] += 1
            cap = (top - w2[t]) // 2              # wins t can take without passing x
            if cap < 0:
                continue                          # already ahead whatever happens
            if cap >= degp[t]:
                held[div[t]] += 1
            else:
                need[t] = degp[t] - cap           # losses needed to be held
                (easy if self.fast and cap >= (degp[t] + 1) // 2 else hard).append(t)

        def fits(have: list[int]) -> bool:
            """True when holding these teams leaves at most wild-1 extra teams ahead."""
            return sum(max(0, total[d] - have[d] - 1) for d in range(nd)) <= wild - 1

        if self.fast:
            near = held[:]
            for t in easy:
                near[div[t]] += 1
            if fits(near):
                return False
            for t in hard:
                near[div[t]] += 1
            if not fits(near):
                return True
        cand = sorted(easy + hard, key=lambda t: need[t])
        return not self._search(cand, need, degp, pairp, held, fits)

    def flags(self, x: int, w2: list[int], kinds=KINDS) -> dict[str, bool]:
        """The requested statuses for team ``x`` (``kinds`` picks which)."""
        return {k: getattr(self, k)(x, w2) for k in kinds}


def statuses(ids, division_of, spots, wins, games, fast: bool = True) -> dict[int, dict[str, bool]]:
    """All six statuses for every team: ``wins`` is team id -> wins (ties count half) and
    ``games`` the (team, team) pairs still to play."""
    ids = list(ids)
    board = Board(ids, division_of, spots, games, fast)
    w2 = [round(2 * wins[t]) for t in ids]
    return {t: board.flags(i, w2) for i, t in enumerate(ids)}


# ── the feature ────────────────────────────────────────────────────────────────
MAX_GAMES = 8   # this week's games beyond this many would make the outcome table too big


def _ways(hits: set[tuple[int, ...]], n: int) -> list[tuple[int | None, ...]]:
    """Every minimal partial result (None = that game can go either way) whose completions all
    land in ``hits`` (full results: 0 = the first team of the game wins, 1 = the second), fewest
    fixed games first."""
    sure = []
    for part in product((None, 0, 1), repeat=n):
        free = [i for i, v in enumerate(part) if v is None]
        ok = True
        for fill in product((0, 1), repeat=len(free)):
            full = list(part)
            for i, v in zip(free, fill, strict=True):
                full[i] = v
            if tuple(full) not in hits:
                ok = False
                break
        if ok:
            sure.append(part)
    picked = set(sure)
    minimal = [p for p in sure
               if not any(p[i] is not None and p[:i] + (None,) + p[i + 1:] in picked for i in range(n))]
    return sorted(minimal, key=lambda p: (sum(v is not None for v in p), [-1 if v is None else v for v in p]))


def _magic(board: Board, x: int, w2: list[int], kind: str) -> int | None:
    """Fewest more wins for team index ``x`` that settle ``kind`` (playoffs_in / last_safe) with
    no help: every way of winning that many of its games, with the rest of its games lost and
    everything else open, settles it. None when winning out doesn't."""
    opps = [b for b in range(board.n) for _ in range(board.pair[x][b])]  # one per game x still plays
    rest = [(board.ids[a], board.ids[b]) for a in range(board.n) for b in range(a + 1, board.n)
            if x not in (a, b) for _ in range(board.pair[a][b])]
    after = Board(board.ids, dict(zip(board.ids, board.div, strict=True)), board.spots, rest)
    check = getattr(after, kind)
    for k in range(len(opps) + 1):
        if all(check(x, _apply(w2, x, [o for i, o in enumerate(opps) if i not in won], k))
               for won in combinations(range(len(opps)), k)):
            return k
    return None


def _apply(w2: list[int], x: int, beat_x: list[int], k: int) -> list[int]:
    """``w2`` after ``x`` wins ``k`` games and loses one to each team in ``beat_x``."""
    out = w2[:]
    out[x] += 2 * k
    for o in beat_x:
        out[o] += 2
    return out


def build(ctx) -> dict | None:
    reg, spots = int(ctx.reg_weeks or 0), int(ctx.playoff_teams or 0)
    ids = [int(t["id"]) for t in ctx.teams]
    if not reg or len(ids) < 2:
        return None
    through = min(ctx.through, reg)
    standing = {s["id"]: s for s in _standings(ids, ctx.matchups, ctx.divisions, through)}
    w2 = [2 * standing[t]["wins"] + standing[t]["ties"] for t in ids]
    left = [g for w in range(through + 1, reg + 1) for g in ctx.schedule.get(w, [])]
    board = Board(ids, ctx.divisions, spots, left)
    now = {t: board.flags(i, w2) for i, t in enumerate(ids)}

    week = through + 1 if through < reg else None
    this = [g for g in ctx.schedule.get(week, []) if g[0] in standing and g[1] in standing] if week else []
    scenarios = []
    if this and len(this) <= MAX_GAMES:
        later = [g for w in range(week + 1, reg + 1) for g in ctx.schedule.get(w, [])]
        nxt = Board(ids, ctx.divisions, spots, later)
        index = {t: i for i, t in enumerate(ids)}
        open_kinds = {t: [k for k in KINDS if not now[t][k]] for t in ids}
        hits: dict[tuple[int, str], set[tuple[int, ...]]] = {}
        for result in product((0, 1), repeat=len(this)):
            after = w2[:]
            for (a, b), r in zip(this, result, strict=True):
                after[index[b if r else a]] += 2
            for t in ids:
                for k, ok in nxt.flags(index[t], after, open_kinds[t]).items():
                    if ok:
                        hits.setdefault((t, k), set()).add(result)
        for (t, k), got in sorted(hits.items(), key=lambda kv: (KINDS.index(kv[0][1]), kv[0][0])):
            ways = [[{"winner": (b if r else a), "loser": (a if r else b)}
                     for (a, b), r in zip(this, part, strict=True) if r is not None]
                    for part in _ways(got, len(this))]
            scenarios.append({"team": t, "kind": k, "ways": ways})

    teams = []
    for i, t in enumerate(ids):
        s = standing[t]
        magic = {"playoffs": 0 if now[t]["playoffs_in"] else None, "safe": 0 if now[t]["last_safe"] else None}
        if left:
            if board.wild is not None and not now[t]["playoffs_in"] and not now[t]["playoffs_out"]:
                magic["playoffs"] = _magic(board, i, w2, "playoffs_in")
            if not now[t]["last_safe"] and not now[t]["last_locked"]:
                magic["safe"] = _magic(board, i, w2, "last_safe")
        teams.append({"team": t, "wins": s["wins"], "losses": s["losses"], "ties": s["ties"],
                      "status": now[t], "magic": magic})
    return {"week": week, "weeks_left": reg - through, "spots": spots, "teams": teams,
            "scenarios": scenarios}
