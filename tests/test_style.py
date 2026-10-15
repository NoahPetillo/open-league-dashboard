"""Manager style: percentiles, archetype assignment, and what happens when a feed is missing."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from league import style


def _ctx(trades=None, adds=None, *, moves=None, faab=None, offers=None, loyalty=None):
    """A context from per-team numbers keyed by team id. ``moves`` lands in ESPN's counters;
    ``faab`` / ``offers`` / ``loyalty`` are the finished features' outputs (None = missing)."""
    ids = sorted({*(trades or {}), *(adds or {}), *(moves or {})})
    teams = []
    for i in ids:
        row = {"id": i, "name": f"Team {i}", "manager": f"Manager {i}"}
        if trades is not None:
            row["trades"] = trades[i]
        if adds is not None:
            row["adds"] = adds[i]
        teams.append(row)
    counters = {i: {"moveToActive": v} for i, v in (moves or {}).items()}
    outputs = {"faab": faab, "offers": offers, "loyalty": loyalty}
    return SimpleNamespace(teams=teams, counters=counters, outputs=outputs)


def _by_team(out):
    return {r["team"]: r for r in out["teams"]}


def _keys(out):
    return [d["key"] for d in out["dims"]]


# ── percentile and rank ────────────────────────────────────────────────────────
def test_percentile_counts_half_of_the_ties_and_skips_nulls():
    s = style.standings({1: 5, 2: 5, 3: 1, 4: None, 5: 9})
    assert set(s) == {1, 2, 3, 5}                       # the null team is not ranked at all
    # n = 4, so each percentile is out of 3 other teams.
    assert s[5].pct == 1.0 and s[3].pct == 0.0
    assert s[1].pct == s[2].pct == (1 + 0.5) / 3        # one below, one tied (half), one above
    assert (s[1].below, s[1].tied, s[1].above) == (1, 1, 1)


def test_rank_one_is_the_highest_and_tied_teams_share_it():
    s = style.standings({1: 7, 2: 7, 3: 2, 4: 9})
    assert (s[4].rank, s[1].rank, s[2].rank, s[3].rank) == (1, 2, 2, 4)
    assert (s[3].rank_low, s[4].rank_low) == (1, 4)


def test_a_lone_value_has_nothing_to_compare_with():
    assert style.standings({1: 3, 2: None}) == {}
    assert style.standings({}) == {}


def test_strength_is_the_distance_from_the_middle():
    s = style.standings({1: 1, 2: 2, 3: 3, 4: 4, 5: 5})
    assert [round(s[i].strength, 4) for i in (1, 2, 3, 4, 5)] == [0.5, 0.25, 0.0, 0.25, 0.5]
    assert [s[i].direction for i in (1, 2, 3, 4, 5)] == ["low", "low", None, "high", "high"]
    for x in s.values():                                 # same thing as |pct - 0.5|
        assert x.strength == pytest.approx(abs(x.pct - 0.5))


# ── archetypes ─────────────────────────────────────────────────────────────────
# Six teams, two dimensions. Strengths (distance from the middle) work out to:
#   trades  1 .5 high · 2 .3 high · 3 .1 high · 4 .1 low · 5 .3 low · 6 .5 low
#   adds    3 .5 high · 2 .3 high · 4 .1 high · 6 .1 low · 5 .3 low · 1 .5 low
TRADES = {1: 10, 2: 9, 3: 5, 4: 4, 5: 3, 6: 0}
ADDS = {1: 6, 2: 15, 3: 20, 4: 9, 5: 7, 6: 8}


def _six():
    return _by_team(style.build(_ctx(TRADES, ADDS)))


def _arch(row):
    return row["archetype"]["key"]


def test_each_title_goes_to_one_team_when_it_can():
    six = _six()
    # Team 1 is .5 on both trades-high and adds-low; ties go to the lower dimension order.
    assert _arch(six[1]) == "day_trader"
    assert _arch(six[3]) == "waiver_hawk" and _arch(six[6]) == "recluse"
    assert six[1]["archetype"]["dim"] == "trades" and six[1]["archetype"]["dir"] == "high"
    assert six[6]["archetype"]["dir"] == "low"


def test_a_team_whose_best_title_is_taken_moves_to_its_next_one():
    # Team 5 is .3 on trades-low and on adds-low; Recluse went to team 6 (.5), so it takes
    # The Hoarder instead of sharing.
    six = _six()
    assert _arch(six[5]) == "hoarder"
    assert six[5]["archetype"]["why"] == "2nd-fewest pickups (7)"


def test_a_team_with_nothing_left_shares_its_strongest_title():
    # Team 2 is .3 on trades-high (Day Trader, team 1's) and on adds-high (Waiver Hawk, team 3's).
    six = _six()
    assert _arch(six[2]) == "day_trader"                 # the tie goes to the first dimension
    assert six[2]["archetype"]["why"] == "2nd-most trades (9)"


def test_nothing_near_an_edge_is_the_middle_child():
    mc = _six()[4]["archetype"]
    assert (mc["key"], mc["title"]) == ("middle_child", "The Middle Child")
    assert mc["blurb"] == "Average at everything. Even the roasts are lukewarm."
    assert mc["dim"] is None and mc["dir"] is None
    assert mc["why"] == "Nothing stands out. Closest to an edge: 3rd-fewest trades (4)."


def test_equal_strengths_go_to_the_lower_team_id_first():
    S = style.Standing
    # Teams 3 and 7 are both .5 from the middle on trades; team 7 is also .25 high on adds.
    by_dim = {"trades": {7: S(8, 0, 0), 3: S(8, 0, 0)}, "adds": {7: S(6, 2, 0)}}
    got = style._assign(by_dim, ["trades", "adds"])
    assert got == {3: ("trades", "high"), 7: ("adds", "high")}


def test_the_threshold_is_exactly_one_fifth_from_the_middle():
    # 11 teams on one dimension: team i has |below - above| = |2i - 10| of 20, so teams 3 and 7
    # sit exactly at 0.2 and teams 4 and 6 at 0.1.
    trades = {i: i for i in range(11)}
    out = _by_team(style.build(_ctx(trades, None)))
    assert [_arch(out[i]) for i in (0, 10)] == ["recluse", "day_trader"]
    assert _arch(out[3]) == "recluse" and _arch(out[7]) == "day_trader"   # shares: team 0 and 10 hold them
    assert _arch(out[4]) == _arch(out[5]) == _arch(out[6]) == "middle_child"


def test_just_under_the_threshold_is_the_middle_child():
    # Four teams tied on 5 with five below and two above: |5 - 2| / 20 = 0.15.
    trades = dict(enumerate([0, 1, 2, 3, 4, 5, 5, 5, 5, 8, 9]))
    out = _by_team(style.build(_ctx(trades, None)))
    assert style.standings(trades)[5].strength == 0.15
    assert all(_arch(out[i]) == "middle_child" for i in (5, 6, 7, 8))
    assert _arch(out[10]) == "day_trader"


# ── missing features, thin data ────────────────────────────────────────────────
def _full(**override):
    """Six teams with every dimension filled in; ``override`` swaps in (or, with None, removes)
    a feed. FAAB, yes-rate and draft loyalty all rise with the team id."""
    ids = range(1, 7)
    answers = [(0, 4), (1, 4), (2, 3), (3, 3), (4, 2), (5, 1)]          # (accepted, declined)
    parts = {
        "faab": {"teams": [{"team": i, "spent_on_bids": v} for i, v in zip(ids, [0, 5, 10, 15, 20, 40], strict=True)]},
        "offers": {"teams": [{"team": i, "accepted": a, "declined": d, "answered": a + d,
                              "accept_rate": round(a / (a + d), 4)} for i, (a, d) in zip(ids, answers, strict=True)]},
        "loyalty": {"teams": [{"team": i, "drafted": 10, "kept": k} for i, k in zip(ids, [1, 3, 5, 6, 8, 10], strict=True)]},
    }
    parts.update(override)
    return _ctx(TRADES, ADDS, moves={1: 20, 2: 25, 3: 30, 4: 35, 5: 40, 6: 65}, **parts)


def test_every_dimension_shows_up_when_every_feed_is_there():
    out = style.build(_full())
    assert _keys(out) == ["trades", "adds", "faab", "moves", "yes_rate", "loyalty"]
    assert all(set(d) == {"key", "label", "desc"} for d in out["dims"])
    t6 = _by_team(out)[6]
    assert t6["metrics"] == {"trades": 0, "adds": 8, "faab": 40, "moves": 65,
                             "yes_rate": round(5 / 6, 4), "loyalty": 1.0}


@pytest.mark.parametrize("gone, keys", [
    ("faab", ["trades", "adds", "moves", "yes_rate", "loyalty"]),
    ("offers", ["trades", "adds", "faab", "moves", "loyalty"]),
    ("loyalty", ["trades", "adds", "faab", "moves", "yes_rate"]),
])
def test_a_missing_feed_drops_its_dimension_everywhere(gone, keys):
    out = style.build(_full(**{gone: None}))
    assert _keys(out) == keys
    for row in out["teams"]:
        assert list(row["metrics"]) == list(row["pct"]) == list(row["rank"]) == keys
        assert row["archetype"]["dim"] in keys + [None]


def test_with_no_other_feed_the_team_rows_still_make_a_profile():
    out = style.build(_ctx(TRADES, ADDS))
    assert _keys(out) == ["trades", "adds"]
    assert len(out["teams"]) == 6
    ctx = _ctx(TRADES, ADDS)
    del ctx.outputs, ctx.counters                         # a context from before these existed
    assert _keys(style.build(ctx)) == ["trades", "adds"]


def test_a_feed_that_came_back_empty_or_broken_is_just_missing():
    out = style.build(_full(faab={"budget": 100}, offers={"teams": "nope"}, loyalty={"teams": [None, 3]}))
    assert _keys(out) == ["trades", "adds", "moves"]


def test_lineup_moves_need_espns_counter():
    ctx = _full()
    ctx.counters = {}
    assert "moves" not in _keys(style.build(ctx))


def test_yes_rate_needs_three_answered_offers():
    offers = {"teams": [
        {"team": 1, "accepted": 1, "declined": 1, "answered": 2, "accept_rate": 0.5},   # too few
        {"team": 2, "accepted": 0, "declined": 3, "answered": 3, "accept_rate": 0.0},
        {"team": 3, "accepted": 1, "declined": 2, "answered": 3, "accept_rate": 0.3333},
        {"team": 4, "accepted": 2, "declined": 2, "answered": 4, "accept_rate": 0.5},
        {"team": 5, "accepted": 0, "declined": 0, "answered": 0, "accept_rate": None},
    ]}
    out = style.build(_full(offers=offers))
    by = _by_team(out)
    assert [by[i]["metrics"]["yes_rate"] for i in range(1, 7)] == [None, 0.0, 0.3333, 0.5, None, None]
    assert by[1]["pct"]["yes_rate"] is None and by[1]["rank"]["yes_rate"] is None
    assert (by[4]["rank"]["yes_rate"], by[2]["rank"]["yes_rate"]) == (1, 3)
    assert by[4]["pct"]["yes_rate"] == 1.0                # ranked against the three that count


def test_a_dimension_needs_three_teams_and_some_spread():
    two = {"teams": [{"team": 1, "accepted": 3, "declined": 1, "answered": 4, "accept_rate": 0.75},
                     {"team": 2, "accepted": 1, "declined": 3, "answered": 4, "accept_rate": 0.25}]}
    assert "yes_rate" not in _keys(style.build(_full(offers=two)))           # only two teams to compare
    flat = {"teams": [{"team": i, "spent_on_bids": 0} for i in range(1, 7)]}
    assert "faab" not in _keys(style.build(_full(faab=flat)))                # everyone spent $0


def test_loyalty_is_kept_over_drafted_and_equal_fractions_tie():
    loyalty = {"teams": [{"team": 1, "drafted": 3, "kept": 1}, {"team": 2, "drafted": 6, "kept": 2},
                         {"team": 3, "drafted": 4, "kept": 3}, {"team": 4, "drafted": 5, "kept": 0},
                         {"team": 5, "drafted": 0, "kept": 0}]}              # no picks: unknown, not 0
    by = _by_team(style.build(_full(loyalty=loyalty)))
    assert [by[i]["metrics"]["loyalty"] for i in range(1, 7)] == [0.3333, 0.3333, 0.75, 0.0, None, None]
    assert by[1]["rank"]["loyalty"] == by[2]["rank"]["loyalty"] == 2
    assert by[1]["pct"]["loyalty"] == by[2]["pct"]["loyalty"] == round(1.5 / 3, 4)


def test_nothing_to_compare_means_no_section():
    assert style.build(_ctx({1: 1, 2: 2}, {1: 5, 2: 6})) is None             # two teams
    assert style.build(_ctx({1: 0, 2: 0, 3: 0}, {1: 4, 2: 4, 3: 4})) is None   # no spread anywhere
    ctx = _ctx({1: 1, 2: 2, 3: 3}, None)
    ctx.teams[2].pop("trades")                                                # one team has no numbers
    assert style.build(ctx) is None


def test_a_team_with_no_numbers_gets_no_profile():
    ctx = _ctx(TRADES, ADDS)
    ctx.teams.append({"id": 9, "name": "Ghost", "manager": "Nobody"})
    assert sorted(_by_team(style.build(ctx))) == [1, 2, 3, 4, 5, 6]


# ── the "why" line ─────────────────────────────────────────────────────────────
def _why(key, direction, below, above, tied, shown):
    return style._why(style.DIM_BY_KEY[key], direction, style.Standing(below, above, tied), shown)


def test_why_says_the_real_rank_and_owns_up_to_ties():
    assert _why("moves", "high", 11, 0, 0, "65") == "Most lineup moves in the league (65)"
    assert _why("trades", "low", 1, 9, 0, "1") == "2nd-fewest trades (1)"
    assert _why("trades", "low", 0, 6, 5, "2") == "Fewest trades in the league, tied with 5 others (2)"
    assert _why("trades", "low", 0, 10, 1, "2") == "Fewest trades in the league, tied with 1 other (2)"
    assert _why("trades", "high", 9, 0, 2, "8") == "Most trades in the league, tied with 2 others (8)"
    assert _why("adds", "high", 9, 1, 1, "20") == "2nd-most pickups, tied with 1 other (20)"
    assert _why("adds", "high", 8, 2, 0, "14") == "3rd-most pickups (14)"


def test_why_reads_right_for_money_and_rates():
    assert _why("faab", "low", 0, 5, 6, style._show("faab", 0)) == "Least FAAB spent in the league, tied with 6 others ($0)"
    assert _why("faab", "high", 11, 0, 0, style._show("faab", 40)) == "Most FAAB spent in the league ($40)"
    shown = style._show("yes_rate", 0.2941, "5 of 17")
    assert _why("yes_rate", "high", 11, 0, 0, shown) == "Highest yes-rate on trade offers in the league (29%, 5 of 17)"
    assert _why("loyalty", "low", 1, 9, 0, style._show("loyalty", 0.4737)) == "2nd-lowest share of draft picks kept (47%)"


def test_ordinals():
    got = [style._ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111)]
    assert got == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "111th"]


def test_percents_round_half_up_the_way_the_page_does():
    # The page prints Math.floor(x * 100 + 0.5), so a .125 rate is 13%, not Python's 12%.
    assert style._show("yes_rate", 0.125) == "13%"
    assert style._show("loyalty", 0.5789) == "58%" and style._show("yes_rate", 0.0) == "0%"
    assert style._show("yes_rate", 1.0) == "100%"


def test_every_why_line_matches_the_numbers_it_came_from():
    out = style.build(_full())
    checked = 0
    for row in out["teams"]:
        a = row["archetype"]
        if a["dim"] is None:
            continue
        checked += 1
        key, v, pct = a["dim"], row["metrics"][a["dim"]], row["pct"][a["dim"]]
        assert (pct > 0.5) == (a["dir"] == "high") and abs(pct - 0.5) >= style.MIN_SIGNAL
        # the number in the brackets is the team's own number (plus the counts behind a rate)...
        assert re.search(r"\(([^)]*)\)$", a["why"]).group(1).split(",")[0] == style._show(key, v)
        # ...and its rank is recounted here from every team's raw numbers.
        vals = [r["metrics"][key] for r in out["teams"] if r["metrics"][key] is not None]
        place = 1 + sum(x > v for x in vals) if a["dir"] == "high" else 1 + sum(x < v for x in vals)
        if place == 1:
            assert a["why"].split(" ")[0] in ("Most", "Fewest", "Least", "Highest", "Lowest")
        else:
            assert a["why"].startswith(f"{style._ordinal(place)}-")
    assert checked >= 4


# ── shape ──────────────────────────────────────────────────────────────────────
def test_output_shape():
    out = style.build(_full())
    assert set(out) == {"dims", "teams"}
    keys = _keys(out)
    for row in out["teams"]:
        assert set(row) == {"team", "metrics", "pct", "rank", "archetype"}
        assert list(row["metrics"]) == list(row["pct"]) == list(row["rank"]) == keys
        assert set(row["archetype"]) == {"key", "title", "blurb", "dim", "dir", "why"}
        assert row["archetype"]["why"] and row["archetype"]["blurb"] and row["archetype"]["title"]
        assert all(0 <= p <= 1 for p in row["pct"].values())
        assert all(isinstance(r, int) and 1 <= r <= 6 for r in row["rank"].values())
    assert [r["team"] for r in out["teams"]] == [1, 2, 3, 4, 5, 6]
    json.dumps(out)                                       # it ships as JSON


def test_every_archetype_has_a_blurb_and_a_dimension_it_belongs_to():
    assert len(style.ARCHETYPES) == 2 * len(style.DIMS)
    assert len({a.key for a in style.ARCHETYPES.values()}) == len(style.ARCHETYPES)
    for (dim, direction), a in style.ARCHETYPES.items():
        assert (a.dim, a.dir) == (dim, direction) and a.title.strip() and a.blurb.strip()
        assert dim in style.DIM_BY_KEY


def test_the_order_teams_arrive_in_changes_nothing():
    ctx = _full()
    forward = {r["team"]: r["archetype"] for r in style.build(ctx)["teams"]}
    ctx.teams.reverse()
    assert {r["team"]: r["archetype"] for r in style.build(ctx)["teams"]} == forward
