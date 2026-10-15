"""Manager style profiles: a fingerprint per manager and a fun archetype.

``build(ctx)`` returns ``{"dims": [{key, label, desc}], "teams": [{team, metrics, pct, rank,
archetype}]}`` (or None when fewer than 3 teams have anything to compare). It lands at
``window.LEAGUE_DATA.style`` and feeds the manager pages.

Dimensions. Each one is a raw number per team, null when it can't be known:
    trades    trades made (the team row's ``trades``).
    adds      waiver + free-agent pickups (the team row's ``adds``).
    faab      FAAB spent on winning bids (``outputs["faab"]`` spent_on_bids).
    moves     ESPN's own lineup-move count (``counters[team]["moveToActive"]``). ESPN counts
              forced moves for byes and injuries too, so the page says so.
    yes_rate  share of answered trade offers that got a yes (``outputs["offers"]`` accept_rate),
              null for a team that answered fewer than 3 offers.
    loyalty   kept / drafted (``outputs["loyalty"]``): the share of draft picks still on the roster.
A dimension nobody can fill is left out of the output entirely (no faab report, no offers, no
loyalty), and so is one with fewer than 3 teams to compare or the same value for every team.
Rates are rounded to 4 places before anything is ranked, so the site can recount ties from the
numbers it is given.

Where a team sits. Among the n teams that have a value:
    pct   (other teams strictly below + half the other teams tied) / (n - 1), 0 to 1.
    rank  1 for the highest value; teams tied on a value share the better rank.
Strength is how far the percentile is from the middle: |pct - 0.5|. It is also
|below - above| / (2 * (n - 1)), which is exact integer arithmetic, so equal strengths
compare equal.

Archetypes. Each dimension has two, one for each end of the league (high / low):
    moves   The Tinkerer / Set It and Forget It     trades  The Day Trader / The Recluse
    adds    The Waiver Hawk / The Hoarder           faab    The Big Spender / The Penny Pincher
    yes_rate  The Pushover / The Brick Wall         loyalty The Loyalist / The Renovator
Every (team, dimension) with a strength of at least 0.2 is a candidate for the archetype at the
end of the league the team sits on. Candidates are sorted by strength, strongest first (ties:
team id, then dimension order), and handed out greedily: a team takes its candidate if it has
no archetype yet and nobody holds that archetype. A team left without one takes its strongest
candidate anyway, so a title can repeat when it has to. A team with no candidate (nothing
within 0.2 of an edge) is The Middle Child.

Each team's ``archetype`` is ``{key, title, blurb, dim, dir, why}``: ``dim`` is the dimension
it comes from and ``dir`` is "high" or "low" (both None for The Middle Child), and ``why``
is one line with the real numbers: "Most lineup moves in the league (65)" or "2nd-fewest
trades (1)". A tie is said out loud: "Fewest trades in the league, tied with 5 others (2)".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_TEAMS = 3       # fewer teams than this and a percentile means nothing
MIN_ANSWERED = 3    # a yes-rate needs at least this many answered offers
MIN_SIGNAL = 0.2    # strength an archetype needs; under it a team is The Middle Child


@dataclass(frozen=True)
class Dim:
    key: str
    label: str
    desc: str
    noun: str         # what the "why" line counts: "Most {noun} in the league (65)"
    hi: str = "most"
    lo: str = "fewest"


DIMS: tuple[Dim, ...] = (
    Dim("trades", "Trades", "Trades made this season.", "trades"),
    Dim("adds", "Pickups", "Waiver and free-agent pickups.", "pickups"),
    Dim("faab", "FAAB spent", "FAAB dollars spent on winning bids.", "FAAB spent", lo="least"),
    Dim("moves", "Lineup moves",
        "ESPN's own count of lineup moves. Forced moves for byes and injuries are included.",
        "lineup moves"),
    Dim("yes_rate", "Yes to trade offers",
        f"Share of answered trade offers that got a yes. Needs {MIN_ANSWERED} or more answered.",
        "yes-rate on trade offers", hi="highest", lo="lowest"),
    Dim("loyalty", "Draft picks kept", "Share of draft picks still on the roster today.",
        "share of draft picks kept", hi="highest", lo="lowest"),
)
DIM_BY_KEY = {d.key: d for d in DIMS}


@dataclass(frozen=True)
class Archetype:
    key: str
    title: str
    blurb: str
    dim: str | None = None
    dir: str | None = None


ARCHETYPES: dict[tuple[str, str], Archetype] = {
    ("moves", "high"): Archetype(
        "tinkerer", "The Tinkerer", "The lineup is never finished. Every Sunday is a rewrite.",
        "moves", "high"),
    ("moves", "low"): Archetype(
        "set_and_forget", "Set It and Forget It",
        "Sets the lineup once and trusts fate. Bold, or just asleep?", "moves", "low"),
    ("trades", "high"): Archetype(
        "day_trader", "The Day Trader", "Everyone on the roster is a trade chip. Even the new guys.",
        "trades", "high"),
    ("trades", "low"): Archetype(
        "recluse", "The Recluse", "Almost never trades. Phone off, door locked.", "trades", "low"),
    ("adds", "high"): Archetype(
        "waiver_hawk", "The Waiver Hawk",
        "Lives on the waiver wire. The bench has a revolving door.", "adds", "high"),
    ("adds", "low"): Archetype(
        "hoarder", "The Hoarder", "Never lets anyone go. The bench is a museum.", "adds", "low"),
    ("faab", "high"): Archetype(
        "big_spender", "The Big Spender", "Treats the FAAB budget like a company card.",
        "faab", "high"),
    ("faab", "low"): Archetype(
        "penny_pincher", "The Penny Pincher", "Guards the FAAB budget like a retirement fund.",
        "faab", "low"),
    ("yes_rate", "high"): Archetype(
        "pushover", "The Pushover", "The softest touch in the league. Worth sending an offer.",
        "yes_rate", "high"),
    ("yes_rate", "low"): Archetype(
        "brick_wall", "The Brick Wall", "Every offer bounces off. A yes takes a miracle.",
        "yes_rate", "low"),
    ("loyalty", "high"): Archetype(
        "loyalist", "The Loyalist", "Drafted them, kept them. Ride or die, even when they stink.",
        "loyalty", "high"),
    ("loyalty", "low"): Archetype(
        "renovator", "The Renovator", "Draft day was a first draft. The roster keeps getting rebuilt.",
        "loyalty", "low"),
}
MIDDLE_CHILD = Archetype("middle_child", "The Middle Child",
                         "Average at everything. Even the roasts are lukewarm.")


# ── where a team sits ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Standing:
    """One team's place on one dimension, counted against the other teams that have a value."""
    below: int   # other teams with a lower value
    above: int   # other teams with a higher value
    tied: int    # other teams with the same value

    @property
    def n(self) -> int:
        return self.below + self.above + self.tied + 1

    @property
    def pct(self) -> float:
        """(below + half the tied) / (n - 1), from 0 (lowest) to 1 (highest)."""
        return (2 * self.below + self.tied) / (2 * (self.n - 1))

    @property
    def rank(self) -> int:
        """1 is the highest value; teams tied on a value share the better rank."""
        return 1 + self.above

    @property
    def rank_low(self) -> int:
        """The same count from the bottom: 1 is the lowest value."""
        return 1 + self.below

    @property
    def strength(self) -> float:
        """How far from the middle, 0 to 0.5: |pct - 0.5|, from exact integers."""
        return abs(self.below - self.above) / (2 * (self.n - 1))

    @property
    def direction(self) -> str | None:
        """Which end of the league: "high", "low", or None when dead center."""
        return "high" if self.below > self.above else "low" if self.below < self.above else None


def standings(values: dict[int, float | None]) -> dict[int, Standing]:
    """``team -> Standing`` for every team with a value. Teams with None are left out and don't
    count toward anyone's percentile; fewer than two values means nothing to compare."""
    have = {t: v for t, v in values.items() if v is not None}
    if len(have) < 2:
        return {}
    out = {}
    for team, v in have.items():
        others = [w for t, w in have.items() if t != team]
        out[team] = Standing(below=sum(w < v for w in others), above=sum(w > v for w in others),
                             tied=sum(w == v for w in others))
    return out


# ── the raw numbers ────────────────────────────────────────────────────────────
def _num(x) -> int | float | None:
    """A finite number (never a bool), whole numbers as ints; anything else is unknown."""
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x):
        return None
    return int(x) if float(x).is_integer() else x


def _rows(output, key: str = "teams") -> dict[int, dict]:
    """``team id -> row`` from another feature's output (empty when it is missing)."""
    rows = output.get(key) if isinstance(output, dict) else None
    return {int(r["team"]): r for r in rows or [] if isinstance(r, dict) and r.get("team") is not None}


def _fraction(top, bottom) -> float | None:
    top, bottom = _num(top), _num(bottom)
    return round(top / bottom, 4) if top is not None and bottom else None


def _raw(ctx) -> tuple[dict[str, dict[int, int | float | None]], dict[str, dict[int, str]]]:
    """``(values, detail)``: each dimension's number per team (None when unknown) and, where it
    helps a reader, the counts behind a rate ("5 of 17")."""
    outputs = getattr(ctx, "outputs", None) or {}
    counters = getattr(ctx, "counters", None) or {}
    faab = _rows(outputs.get("faab"))
    offers = _rows(outputs.get("offers"))
    loyalty = _rows(outputs.get("loyalty"))
    values: dict[str, dict[int, int | float | None]] = {d.key: {} for d in DIMS}
    detail: dict[str, dict[int, str]] = {"yes_rate": {}, "loyalty": {}}
    for row in ctx.teams:
        tid = int(row["id"])
        values["trades"][tid] = _num(row.get("trades"))
        values["adds"][tid] = _num(row.get("adds"))
        values["faab"][tid] = _num(faab.get(tid, {}).get("spent_on_bids"))
        values["moves"][tid] = _num((counters.get(tid) or {}).get("moveToActive"))

        offer = offers.get(tid, {})
        answered = _num(offer.get("answered"))
        rate = _num(offer.get("accept_rate"))
        enough = answered is not None and answered >= MIN_ANSWERED and rate is not None
        values["yes_rate"][tid] = rate if enough else None
        accepted = _num(offer.get("accepted"))
        if enough and accepted is not None:
            detail["yes_rate"][tid] = f"{accepted} of {answered}"

        kept, drafted = loyalty.get(tid, {}).get("kept"), loyalty.get(tid, {}).get("drafted")
        values["loyalty"][tid] = _fraction(kept, drafted)
        if values["loyalty"][tid] is not None:
            detail["loyalty"][tid] = f"{_num(kept)} of {_num(drafted)}"
    return values, detail


def _usable(values: dict[int, int | float | None]) -> bool:
    """Enough teams to compare, and not the same number for all of them."""
    have = [v for v in values.values() if v is not None]
    return len(have) >= MIN_TEAMS and len(set(have)) > 1


# ── archetypes ─────────────────────────────────────────────────────────────────
def _assign(by_dim: dict[str, dict[int, Standing]], order: list[str]) -> dict[int, tuple[str, str]]:
    """``team -> (dimension, "high" | "low")`` for every team that earns an archetype.

    Candidates are every (team, dimension) at least MIN_SIGNAL from the middle, strongest first
    (ties: team id, then dimension order). A team takes its candidate when it has none yet and
    nobody holds that archetype. Teams still without one take their strongest candidate even if
    it is held. Teams with no candidate at all are left out: they are The Middle Child."""
    pool = []
    for i, key in enumerate(order):
        for team, s in by_dim[key].items():
            if s.direction and s.strength >= MIN_SIGNAL:
                pool.append((-s.strength, team, i, key, s.direction))
    pool.sort()
    given: dict[int, tuple[str, str]] = {}
    held: set[tuple[str, str]] = set()
    for _neg, team, _i, key, direction in pool:
        if team not in given and (key, direction) not in held:
            given[team] = (key, direction)
            held.add((key, direction))
    for _neg, team, _i, key, direction in pool:  # strongest first: a team's first entry is its best
        given.setdefault(team, (key, direction))
    return given


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _show(key: str, value, extra: str | None = None) -> str:
    """A number the way the site prints it: $ for FAAB, whole percents for rates (rounded half
    up, like the page's Math.floor(x * 100 + 0.5)), with the counts behind a rate when known."""
    if key == "faab":
        return f"${value}"
    if key in ("yes_rate", "loyalty"):
        pct = f"{math.floor(value * 100 + 0.5)}%"
        return f"{pct}, {extra}" if extra else pct
    return str(value)


def _why(dim: Dim, direction: str, s: Standing, shown: str) -> str:
    """The real numbers behind a standing: "Most lineup moves in the league (65)", "2nd-fewest
    trades (1)", "Fewest trades in the league, tied with 5 others (2)"."""
    word = dim.hi if direction == "high" else dim.lo
    place = s.rank if direction == "high" else s.rank_low
    head = word.capitalize() if place == 1 else f"{_ordinal(place)}-{word}"
    scope = " in the league" if place == 1 else ""
    tie = f", tied with {s.tied} other{'' if s.tied == 1 else 's'}" if s.tied else ""
    return f"{head} {dim.noun}{scope}{tie} ({shown})"


def _profile(tid: int, pick: tuple[str, str] | None, mine: dict[str, Standing | None],
             values: dict[str, dict], detail: dict[str, dict]) -> dict:
    """A team's archetype with the numbers that earned it."""

    def line(key: str, direction: str) -> str:
        shown = _show(key, values[key][tid], detail.get(key, {}).get(tid))
        return _why(DIM_BY_KEY[key], direction, mine[key], shown)

    if pick:
        a = ARCHETYPES[pick]
        why = line(*pick)
    else:
        a = MIDDLE_CHILD
        leans = [(s.strength, -i, key) for i, (key, s) in enumerate(mine.items()) if s and s.direction]
        if leans:
            _strength, _i, key = max(leans)
            lean = line(key, mine[key].direction)
            why = f"Nothing stands out. Closest to an edge: {lean[0].lower()}{lean[1:]}."
        else:
            why = "Dead center on everything."
    return {"key": a.key, "title": a.title, "blurb": a.blurb, "dim": a.dim, "dir": a.dir, "why": why}


# ── the feature ────────────────────────────────────────────────────────────────
def build(ctx) -> dict | None:
    if len(ctx.teams) < MIN_TEAMS:
        return None
    values, detail = _raw(ctx)
    dims = [d for d in DIMS if _usable(values[d.key])]
    order = [d.key for d in dims]
    by_dim = {key: standings(values[key]) for key in order}
    chosen = _assign(by_dim, order)
    teams = []
    for row in ctx.teams:
        tid = int(row["id"])
        mine = {key: by_dim[key].get(tid) for key in order}
        if not any(mine.values()):
            continue  # nothing is known about this team
        teams.append({
            "team": tid,
            "metrics": {key: values[key][tid] for key in order},
            "pct": {key: round(s.pct, 4) if s else None for key, s in mine.items()},
            "rank": {key: s.rank if s else None for key, s in mine.items()},
            "archetype": _profile(tid, chosen.get(tid), mine, values, detail),
        })
    if len(teams) < MIN_TEAMS:
        return None
    return {"dims": [{"key": d.key, "label": d.label, "desc": d.desc} for d in dims], "teams": teams}
