"""FAAB report card: pickup stints, production credit, FAAB left, FAAB in trades."""

from __future__ import annotations

from types import SimpleNamespace

from league import faab
from league.report import WeekRoster

DAY = 86_400_000
# Three weeks; kickoffs Thursday night (first) to Monday night (last).
KICKS = {1: (1 * DAY, 5 * DAY), 2: (8 * DAY, 12 * DAY), 3: (15 * DAY, 19 * DAY)}


def _roster(players: dict[str, str], started=()) -> WeekRoster:
    return WeekRoster({p: (n, "WR") for p, n in players.items()}, set(started), 0.0)


def _ctx(activity, rosters, pts, *, trades=None, counters=None, budget=100, weeks=(1, 2, 3), kicks=KICKS):
    return SimpleNamespace(
        activity=activity, rosters=rosters, pts=pts, weeks=list(weeks), kicks=kicks,
        names={"a": "Alpha", "b": "Bravo", "-1": "Jets D/ST"}, pos={"a": "WR", "b": "RB", "-1": "D/ST"},
        pro={"a": "KC"}, teams=[{"id": 1}, {"id": 2}, {"id": 3}], trades=trades or [],
        counters=counters if counters is not None else {}, faab_budget=budget)


def _row(date, *moves):
    return {"date": date, "moves": list(moves)}


def _on(team: int, weeks, who="a", started=()):
    """rosters[w][team] has ``who`` for each week in ``weeks`` (started in ``started``)."""
    return {w: {team: _roster({who: who}, [who] if w in started else [])} for w in weeks}


def _merge(*parts):
    out: dict = {}
    for part in parts:
        for w, teams in part.items():
            out.setdefault(w, {}).update(teams)
    return out


def _team(out, tid):
    return next(t for t in out["teams"] if t["team"] == tid)


def _pick(out, tid, pid="a", n=0):
    return [p for p in _team(out, tid)["pickup_list"] if p["id"] == pid][n]


# ── stints ─────────────────────────────────────────────────────────────────────
def test_pickup_counts_only_weeks_he_was_on_the_roster_and_in_the_lineup():
    act = [_row(2 * DAY, (1, "WAIVER ADDED", "a", 7))]  # won after week 1's first kickoff
    rosters = _merge(_on(1, [1, 2, 3], started=[3]))
    pts = {1: {"a": 5.0}, 2: {"a": 10.0}, 3: {"a": 12.5}}
    p = _pick(faab.build(_ctx(act, rosters, pts)), 1)
    # Still before week 1's last kickoff, so week 1 counts; he only started in week 3.
    assert (p["weeks"], p["points"], p["started_points"]) == (3, 27.5, 12.5)
    assert (p["bid"], p["kind"], p["name"], p["pos"], p["pro_team"]) == (7, "waiver", "Alpha", "WR", "KC")


def test_pickup_after_a_weeks_last_kickoff_skips_that_week():
    act = [_row(6 * DAY, (1, "FA ADDED", "a", 0))]  # after week 1 ended
    rosters = _on(1, [1, 2, 3])                      # (a roster glitch must not leak week 1 in)
    pts = {1: {"a": 50.0}, 2: {"a": 10.0}, 3: {"a": 1.0}}
    p = _pick(faab.build(_ctx(act, rosters, pts)), 1)
    assert p["weeks"] == 2 and p["points"] == 11.0 and p["kind"] == "free agent"


def test_add_drop_readd_gives_each_stint_its_own_weeks():
    act = [_row(0, (1, "WAIVER ADDED", "a", 5)),
           _row(6 * DAY, (1, "DROPPED", "a", 0)),   # dropped between weeks 1 and 2
           _row(13 * DAY, (1, "FA ADDED", "a", 0))]  # back after week 2, for week 3
    rosters = _merge(_on(1, [1, 3]))                 # not on the roster in week 2
    pts = {1: {"a": 4.0}, 2: {"a": 99.0}, 3: {"a": 6.0}}
    out = faab.build(_ctx(act, rosters, pts))
    readd, original = _pick(out, 1, n=0), _pick(out, 1, n=1)  # newest first
    assert (readd["bid"], readd["weeks"], readd["points"]) == (0, 1, 6.0)
    assert (original["bid"], original["weeks"], original["points"]) == (5, 1, 4.0)
    assert original["let_go"] and not readd["let_go"]


def test_drop_after_the_first_kickoff_still_counts_that_week_but_not_later_ones():
    act = [_row(0, (1, "FA ADDED", "a", 0)), _row(9 * DAY, (1, "DROPPED", "a", 0))]  # week 2 Fri
    rosters = _on(1, [1, 2, 3])  # box score for week 3 wrongly shows him (e.g. another stint)
    pts = {1: {"a": 1.0}, 2: {"a": 2.0}, 3: {"a": 4.0}}
    p = _pick(faab.build(_ctx(act, rosters, pts)), 1)
    assert p["weeks"] == 2 and p["points"] == 3.0  # weeks 1 and 2; dropped before week 3 kicked off


def test_dropped_before_the_first_kickoff_does_not_count_that_week():
    act = [_row(0, (1, "FA ADDED", "a", 0)), _row(7 * DAY, (1, "DROPPED", "a", 0))]  # before week 2
    p = _pick(faab.build(_ctx(act, _on(1, [1, 2]), {1: {"a": 1.0}, 2: {"a": 2.0}})), 1)
    assert p["weeks"] == 1 and p["points"] == 1.0


def test_trading_him_away_ends_the_stint_for_the_team_that_sent_him():
    act = [_row(0, (1, "WAIVER ADDED", "a", 9)),
           _row(7 * DAY, (1, "TRADE_SENT", "a", 0), (2, "TRADE_RECEIVED", "a", 0))]
    rosters = _merge(_on(1, [1]), _on(2, [2, 3]))
    pts = {1: {"a": 3.0}, 2: {"a": 8.0}, 3: {"a": 8.0}}
    out = faab.build(_ctx(act, rosters, pts))
    p = _pick(out, 1)
    assert p["weeks"] == 1 and p["points"] == 3.0 and p["let_go"]
    assert _team(out, 2)["pickups"] == 0  # a trade acquisition isn't a pickup


def test_same_week_drop_and_readd_credits_the_later_add_once():
    act = [_row(0, (1, "FA ADDED", "a", 0)), _row(9 * DAY, (1, "DROPPED", "a", 0)),
           _row(10 * DAY, (1, "WAIVER ADDED", "a", 4))]
    out = faab.build(_ctx(act, _on(1, [1, 2]), {1: {"a": 1.0}, 2: {"a": 2.0}}))
    old, new = _pick(out, 1, n=1), _pick(out, 1, n=0)
    assert (old["weeks"], new["weeks"]) == (1, 1) and old["points"] == 1.0 and new["points"] == 2.0


def test_missing_kickoff_times_fall_back_to_the_roster_alone():
    act = [_row(9 * DAY, (1, "FA ADDED", "a", 0))]
    p = _pick(faab.build(_ctx(act, _on(1, [1, 2]), {1: {"a": 1.0}, 2: {"a": 2.0}}, kicks={})), 1)
    assert p["weeks"] == 2


def test_team_defense_ids_and_unknown_players():
    act = [_row(0, (1, "FA ADDED", "-1", 0), (1, "FA ADDED", "zzz", 0))]
    rosters = {1: {1: _roster({"-1": "Jets D/ST", "zzz": "?"}, ["-1"])}}
    out = faab.build(_ctx(act, rosters, {1: {"-1": 12.0, "zzz": 1.0}}, weeks=[1]))
    names = {p["id"]: p["name"] for p in _team(out, 1)["pickup_list"]}
    assert names == {"-1": "Jets D/ST", "zzz": "Player zzz"}
    assert _pick(out, 1, "-1")["started_points"] == 12.0


# ── team rollups ───────────────────────────────────────────────────────────────
def _two_bids():
    act = [_row(0, (1, "WAIVER ADDED", "a", 10), (1, "FA ADDED", "b", 0), (2, "WAIVER ADDED", "x", 6))]
    rosters = {1: {1: _roster({"a": "Alpha", "b": "Bravo"}, ["a", "b"]),
                   2: _roster({"x": "Xray"}, [])}}
    pts = {1: {"a": 20.0, "b": 5.0, "x": 9.0}}
    ctx = _ctx(act, rosters, pts, weeks=[1])
    ctx.names["x"] = "Xray"
    return faab.build(ctx)


def test_dollars_per_started_point_and_best_pickup():
    t = _team(_two_bids(), 1)
    assert t["spent_on_bids"] == 10 and t["bids_won"] == 1 and t["pickups"] == 2
    assert t["pickup_started_points"] == 25.0 and t["dollars_per_started_point"] == 0.4
    assert t["best_pickup"]["id"] == "a"


def test_started_points_vs_points_when_benched():
    t = _team(_two_bids(), 2)
    assert t["pickup_points"] == 9.0 and t["pickup_started_points"] == 0.0
    assert t["dollars_per_started_point"] is None and t["best_pickup"] is None


def test_dollars_per_started_point_is_null_when_nothing_was_spent():
    # He started and scored, but the pickup cost $0.
    out = faab.build(_ctx([_row(0, (3, "FA ADDED", "a", 0))], _on(3, [1], started=[1]), {1: {"a": 8.0}},
                          weeks=[1]))
    assert _team(out, 3)["pickup_started_points"] == 8.0
    assert _team(out, 3)["dollars_per_started_point"] is None


def test_pickup_list_is_newest_first():
    act = [_row(2 * DAY, (1, "FA ADDED", "a", 0)), _row(3 * DAY, (1, "FA ADDED", "b", 0))]
    out = faab.build(_ctx(act, {}, {}, weeks=[]))
    assert [p["id"] for p in _team(out, 1)["pickup_list"]] == ["b", "a"]


# ── FAAB left ──────────────────────────────────────────────────────────────────
def test_faab_left_uses_espns_counter_and_falls_back_when_missing():
    act = [_row(0, (1, "WAIVER ADDED", "a", 10)),
           _row(DAY, (1, "FAAB_SENT", "", 5), (2, "FAAB_RECEIVED", "", 5))]
    out = faab.build(_ctx(act, {}, {}, weeks=[], counters={1: {"acquisitionBudgetSpent": 14}}))
    assert (_team(out, 1)["left"], _team(out, 1)["left_source"]) == (86, "espn")  # ESPN wins, even if ≠ ours
    # No counter for team 1/2: budget − bids − sent + received.
    assert (_team(out, 1)["faab_out"], _team(out, 1)["faab_in"]) == (5, 0)
    out = faab.build(_ctx(act, {}, {}, weeks=[], counters={3: {"acquisitionBudgetSpent": 0}}))
    assert (_team(out, 1)["left"], _team(out, 1)["left_source"]) == (85, "computed")
    assert (_team(out, 2)["left"], _team(out, 2)["left_source"]) == (105, "computed")
    assert _team(out, 3)["left"] == 100 and _team(out, 3)["left_source"] == "espn"


def test_commish_adjustment_is_what_bids_and_trades_dont_explain():
    # Team 1 bid $10 and sent $5 in a trade, but ESPN says it's spent only $14 → the
    # commish gave it $1. Team 2 received $5 and ESPN agrees → no adjustment.
    act = [_row(0, (1, "WAIVER ADDED", "a", 10)),
           _row(DAY, (1, "FAAB_SENT", "", 5), (2, "FAAB_RECEIVED", "", 5))]
    out = faab.build(_ctx(act, {}, {}, weeks=[], counters={1: {"acquisitionBudgetSpent": 14},
                                                           2: {"acquisitionBudgetSpent": -5}}))
    one, two = _team(out, 1), _team(out, 2)
    assert one["commish"] == 1 and two["commish"] == 0
    for t in (one, two):
        assert t["left"] == 100 - t["spent_on_bids"] - t["faab_out"] + t["faab_in"] + t["commish"]
    # With no ESPN counter we can't see adjustments at all.
    out = faab.build(_ctx(act, {}, {}, weeks=[]))
    assert _team(out, 1)["commish"] == 0


def test_counter_without_the_budget_field_falls_back():
    out = faab.build(_ctx([_row(0, (1, "WAIVER ADDED", "a", 3))], {}, {}, weeks=[],
                          counters={1: {"trades": 2}}))
    assert (_team(out, 1)["left"], _team(out, 1)["left_source"]) == (97, "computed")


def test_no_faab_budget_means_no_report():
    assert faab.build(_ctx([], {}, {}, budget=0)) is None


# ── FAAB in trades ─────────────────────────────────────────────────────────────
def _trade(tid, date, sends):
    sides = {}
    for frm, to, amount in sends:
        sides.setdefault(frm, {"team": frm, "faab_sent": 0, "faab_received": 0})["faab_sent"] += amount
        sides.setdefault(to, {"team": to, "faab_sent": 0, "faab_received": 0})["faab_received"] += amount
    return {"id": tid, "date": date, "sides": list(sides.values())}


def test_faab_trades_pair_sender_and_receiver_with_the_trade_id():
    act = [_row(5 * DAY, (3, "TRADE_SENT", "a", 0), (1, "TRADE_RECEIVED", "a", 0),
                (3, "FAAB_SENT", "", 10), (1, "FAAB_RECEIVED", "", 10)),
           _row(6 * DAY, (2, "TRADE_SENT", "b", 0), (3, "TRADE_RECEIVED", "b", 0))]
    trades = [_trade(14, 5 * DAY, [(3, 1, 10)]), {"id": 15, "date": 6 * DAY, "sides": [{"team": 2}, {"team": 3}]}]
    out = faab.build(_ctx(act, {}, {}, weeks=[], trades=trades))
    assert out["faab_trades"] == [{"trade_id": 14, "date": 5 * DAY, "from": 3, "to": 1, "amount": 10}]
    assert (_team(out, 3)["faab_out"], _team(out, 1)["faab_in"]) == (10, 10)


def test_faab_in_both_directions_pairs_by_amount():
    act = [_row(DAY, (1, "FAAB_SENT", "", 10), (2, "FAAB_RECEIVED", "", 10),
                (2, "FAAB_SENT", "", 3), (1, "FAAB_RECEIVED", "", 3))]
    out = faab.build(_ctx(act, {}, {}, weeks=[]))
    assert [(x["from"], x["to"], x["amount"]) for x in out["faab_trades"]] == [(1, 2, 10), (2, 1, 3)]
    assert all(x["trade_id"] is None for x in out["faab_trades"])  # no graded trade supplied


def test_two_trades_on_the_same_date_are_told_apart_by_the_faab_they_carry():
    act = [_row(DAY, (1, "FAAB_SENT", "", 10), (2, "FAAB_RECEIVED", "", 10))]
    trades = [{"id": 1, "date": DAY, "sides": [{"team": 1, "faab_sent": 0}, {"team": 2, "faab_sent": 0}]},
              _trade(2, DAY, [(1, 2, 10)])]
    assert faab.build(_ctx(act, {}, {}, weeks=[], trades=trades))["faab_trades"][0]["trade_id"] == 2


# ── highlights ─────────────────────────────────────────────────────────────────
def _pickup(bid, started, weeks=1, **kw):
    return {"bid": bid, "started_points": started, "points": started, "weeks": weeks, "date": 0,
            "team": 1, "id": kw.pop("id", str(bid)), **kw}


def test_highlights_best_value_best_free_bust_and_biggest_bid():
    picks = [_pickup(5, 20.0, id="gem"),        # 4.0 per $
             _pickup(30, 3.0, id="bust"),       # 0.1 per $
             _pickup(12, 6.0, id="ok"),         # 0.5 per $
             _pickup(2, 0.0, id="dud"),         # 0 per $
             _pickup(0, 40.0, id="free"), _pickup(0, 55.0, id="free2"),
             _pickup(60, 0.0, weeks=0, id="pending")]  # bid on someone not yet on a finished week
    h = faab._highlights(picks)
    assert h["best_value"]["id"] == "gem" and h["best_free"]["id"] == "free2"
    assert h["biggest_bid"]["id"] == "pending"  # a bid is a bid, even one that can't be judged yet
    assert h["median_pts_per_dollar"] == 0.3
    assert h["bust"]["id"] == "bust"            # biggest bid among those at or below the median


def test_highlights_bust_needs_two_paid_pickups_and_is_never_the_best_value():
    assert faab._highlights([_pickup(10, 5.0)])["bust"] is None
    h = faab._highlights([_pickup(10, 5.0, id="a"), _pickup(20, 10.0, id="b")])  # same $ value
    assert h["best_value"]["id"] == "b" and h["bust"]["id"] == "a"


def test_highlights_are_empty_without_data():
    h = faab._highlights([])
    assert h == {"best_value": None, "best_free": None, "bust": None, "biggest_bid": None,
                 "median_pts_per_dollar": None}


def test_build_is_json_serializable_with_empty_activity():
    import json

    out = faab.build(_ctx([], {}, {}, weeks=[]))
    assert len(out["teams"]) == 3 and out["faab_trades"] == []
    json.dumps(out)
