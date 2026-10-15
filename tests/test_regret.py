"""Trade regret meter: raw points each side's received players scored since the trade."""

from __future__ import annotations

import json
from types import SimpleNamespace

from league import regret

# Week w's games kick off in 100*w .. 100*w + 60 (arbitrary units: only comparisons matter).
KICKS = {1: (100, 160), 2: (200, 260), 3: (300, 360), 4: (400, 460)}


def _ctx(trades, pts, kickoff=None, kicks=KICKS, through=3):
    return SimpleNamespace(through=through, trades=trades, pts=pts, kickoff=kickoff or {}, kicks=kicks)


def _p(pid, name=None, pos="RB"):
    return {"id": pid, "name": name or pid.title(), "pos": pos}


def _side(team, *received, faab=0):
    return {"team": team, "received": list(received), "faab_received": faab}


def _trade(tid, date, first_week, *sides):
    return {"id": tid, "date": date, "first_week": first_week,
            "status": "graded" if first_week else "pending", "sides": list(sides)}


def _by_team(row):
    return {s["team"]: s for s in row["sides"]}


def test_game_before_the_trade_does_not_count_but_later_weeks_do():
    # Trade at 230, mid-week 2. "early" played at 210 (before it), "late" at 250 (after it).
    trade = _trade(1, 230, 2, _side(1, _p("early"), _p("late")), _side(2, _p("x")))
    pts = {2: {"early": 20.0, "late": 5.0, "x": 10.0}, 3: {"early": 7.0, "late": 8.0, "x": 11.0}}
    kickoff = {2: {"early": 210, "late": 250, "x": 255}, 3: {"early": 310, "late": 330, "x": 340}}
    out = regret.build(_ctx([trade], pts, kickoff))
    (row,) = out["trades"]
    one = _by_team(row)[1]
    players = {p["id"]: p for p in one["players"]}
    assert row["weeks"] == [2, 3] and row["first_week"] == 2
    # His week-2 game came first: it counts for nothing and is flagged, so the page can show a dash.
    assert players["early"]["weekly"] == [0.0, 7.0] and players["early"]["total"] == 7.0
    assert players["early"]["skipped"] == [2] and "skipped" not in players["late"]
    assert players["late"]["weekly"] == [5.0, 8.0] and players["late"]["total"] == 13.0
    assert one["weekly"] == [5.0, 15.0] and one["cumulative"] == [5.0, 20.0] and one["total"] == 20.0
    # Team 2's player had no game before the trade: both weeks count.
    assert _by_team(row)[2]["total"] == 21.0
    assert row["leader"] == 2 and row["margin"] == 1.0


def test_game_kicking_off_exactly_at_the_trade_does_not_count():
    trade = _trade(1, 250, 2, _side(1, _p("a")), _side(2, _p("b")))
    pts = {2: {"a": 9.0, "b": 4.0}}
    out = regret.build(_ctx([trade], pts, {2: {"a": 250, "b": 251}}, through=2))
    row = out["trades"][0]
    assert _by_team(row)[1]["total"] == 0.0 and _by_team(row)[2]["total"] == 4.0


def test_player_sitting_in_free_agency_counts_when_every_game_came_after_the_trade():
    # "fa" has no kickoff entry in week 2 or 3: nobody rostered him, so his points come from
    # his player card. A trade at 190 is before week 2's first kickoff (200): counts. A trade
    # at 230 is after it, so his untimed game that week might have come first: left out.
    pts = {2: {"fa": 12.0, "kept": 3.0}, 3: {"fa": 6.0, "kept": 4.0}}
    kickoff = {2: {"kept": 250}, 3: {"kept": 350}}
    early = _trade(1, 190, 2, _side(1, _p("fa"), _p("kept")), _side(2, _p("kept")))
    late = _trade(2, 230, 2, _side(1, _p("fa"), _p("kept")), _side(2, _p("kept")))
    out = regret.build(_ctx([early, late], pts, kickoff))
    by_id = {t["id"]: _by_team(t)[1]["players"] for t in out["trades"]}
    fa = lambda tid: next(p for p in by_id[tid] if p["id"] == "fa")  # noqa: E731
    assert fa(1)["weekly"] == [12.0, 6.0] and fa(1)["total"] == 18.0
    assert fa(2)["weekly"] == [0.0, 6.0] and fa(2)["total"] == 6.0 and fa(2)["skipped"] == [2]
    assert "skipped" not in fa(1)


def test_bye_week_counts_as_zero_points():
    # No kickoff entry in week 3 (bye), 0 points: the week counts, the total doesn't move.
    trade = _trade(1, 150, 2, _side(1, _p("a")), _side(2, _p("b")))
    pts = {2: {"a": 8.0, "b": 2.0}, 3: {"a": 0.0, "b": 5.0}}
    kickoff = {2: {"a": 210, "b": 220}, 3: {"b": 320}}
    row = regret.build(_ctx([trade], pts, kickoff))["trades"][0]
    assert _by_team(row)[1]["players"][0]["weekly"] == [8.0, 0.0]
    assert _by_team(row)[1]["total"] == 8.0 and _by_team(row)[2]["total"] == 7.0


def test_three_team_trade_ranks_every_side():
    trade = _trade(1, 50, 1, _side(1, _p("a")), _side(2, _p("b"), _p("c")), _side(3, _p("d"), faab=15))
    pts = {1: {"a": 10.0, "b": 4.0, "c": 3.0, "d": 6.0}, 2: {"a": 10.0, "b": 4.0, "c": 3.0, "d": 6.0}}
    kickoff = {w: {p: 100 * w + 10 for p in "abcd"} for w in (1, 2)}
    row = regret.build(_ctx([trade], pts, kickoff, through=2))["trades"][0]
    sides = _by_team(row)
    assert [sides[t]["total"] for t in (1, 2, 3)] == [20.0, 14.0, 12.0]
    assert row["leader"] == 1 and row["margin"] == 6.0  # next best is team 2, not team 3
    assert sides[3]["faab_received"] == 15 and sides[1]["faab_received"] == 0
    assert row["lead_changes"] == 0


def test_lead_changes_count_each_time_the_running_leader_changes_hands():
    # Cumulative: A 10, 10, 40, 40 and B 5, 25, 25, 45. A, then B, then A, then B: 3 changes.
    trade = _trade(1, 50, 1, _side(1, _p("a")), _side(2, _p("b")))
    pts = {1: {"a": 10.0, "b": 5.0}, 2: {"a": 0.0, "b": 20.0}, 3: {"a": 30.0, "b": 0.0}, 4: {"a": 0.0, "b": 20.0}}
    kickoff = {w: {"a": 100 * w + 10, "b": 100 * w + 10} for w in (1, 2, 3, 4)}
    row = regret.build(_ctx([trade], pts, kickoff, through=4))["trades"][0]
    assert _by_team(row)[1]["cumulative"] == [10.0, 10.0, 40.0, 40.0]
    assert _by_team(row)[2]["cumulative"] == [5.0, 25.0, 25.0, 45.0]
    assert row["lead_changes"] == 3 and row["leader"] == 2 and row["margin"] == 5.0


def test_weeks_tied_at_the_top_are_skipped_when_counting_lead_changes():
    def changes(a, b):
        trade = _trade(1, 50, 1, _side(1, _p("a")), _side(2, _p("b")))
        pts = {w: {"a": a[w - 1], "b": b[w - 1]} for w in range(1, len(a) + 1)}
        kickoff = {w: {"a": 100 * w + 10, "b": 100 * w + 10} for w in pts}
        return regret.build(_ctx([trade], pts, kickoff, through=len(a)))["trades"][0]["lead_changes"]

    assert changes([5, 0, 5], [0, 5, 0]) == 0   # A, tied at 5-5, A again
    assert changes([5, 0, 0], [0, 5, 5]) == 1   # A, tied, then B pulls ahead
    assert changes([0, 5, 0], [0, 0, 6]) == 1   # week 1 is 0-0 (no leader yet), then A, then B
    assert changes([0, 0], [0, 0]) == 0


def test_exact_tie_has_no_leader_and_zero_margin():
    trade = _trade(1, 50, 1, _side(1, _p("a")), _side(2, _p("b")))
    pts = {1: {"a": 7.5, "b": 4.5}, 2: {"a": 0.0, "b": 3.0}}
    kickoff = {w: {"a": 100 * w + 10, "b": 100 * w + 10} for w in (1, 2)}
    row = regret.build(_ctx([trade], pts, kickoff, through=2))["trades"][0]
    assert _by_team(row)[1]["total"] == _by_team(row)[2]["total"] == 7.5
    # A led after week 1; week 2 ends level, which isn't a change of leader.
    assert row["leader"] is None and row["margin"] == 0.0 and row["lead_changes"] == 0


def test_a_tie_at_the_top_of_a_three_team_trade_has_no_leader():
    trade = _trade(1, 50, 1, _side(1, _p("a")), _side(2, _p("b")), _side(3, _p("c")))
    pts = {1: {"a": 9.0, "b": 9.0, "c": 2.0}}
    kickoff = {1: {"a": 110, "b": 110, "c": 110}}
    row = regret.build(_ctx([trade], pts, kickoff, through=1))["trades"][0]
    assert row["leader"] is None and row["margin"] == 0.0


def test_only_graded_trades_count_and_pending_ones_are_tallied():
    graded = _trade(1, 50, 1, _side(1, _p("a")), _side(2, _p("b")))
    pending = _trade(2, 9999, None, _side(1, _p("c")), _side(2, _p("d")))
    pts = {1: {"a": 1.0, "b": 2.0}}
    out = regret.build(_ctx([graded, pending], pts, {1: {"a": 110, "b": 110}}, through=1))
    assert [t["id"] for t in out["trades"]] == [1] and out["pending"] == 1
    assert regret.build(_ctx([pending], {}, through=1)) is None
    assert regret.build(_ctx([], {}, through=1)) is None


def test_newest_trade_first_and_best_player_first():
    old = _trade(1, 40, 1, _side(1, _p("a1"), _p("a2")), _side(2, _p("b")))
    new = _trade(2, 60, 1, _side(1, _p("c")), _side(2, _p("d")))
    pts = {1: {"a1": 3.0, "a2": 9.0, "b": 1.0, "c": 1.0, "d": 1.0}}
    kickoff = {1: {p: 110 for p in ("a1", "a2", "b", "c", "d")}}
    out = regret.build(_ctx([old, new], pts, kickoff, through=1))
    assert [t["id"] for t in out["trades"]] == [2, 1]
    assert [p["id"] for p in _by_team(out["trades"][1])[1]["players"]] == ["a2", "a1"]


def test_a_trade_graded_over_one_week_has_one_point_per_side():
    trade = _trade(1, 150, 2, _side(1, _p("a")), _side(2, _p("b")))
    pts = {2: {"a": 4.0, "b": 6.0}}
    row = regret.build(_ctx([trade], pts, {2: {"a": 210, "b": 210}}, through=2))["trades"][0]
    assert row["weeks"] == [2]
    assert [s["cumulative"] for s in row["sides"]] == [[4.0], [6.0]]
    assert row["leader"] == 2 and row["margin"] == 2.0 and row["lead_changes"] == 0


def test_points_are_rounded_to_two_places_and_the_output_is_json():
    trade = _trade(1, 50, 1, _side(1, _p("a"), _p("b")), _side(2, _p("c")))
    pts = {1: {"a": 0.1, "b": 0.2, "c": 0.3}, 2: {"a": 0.1, "b": 0.2, "c": 0.3}}
    kickoff = {w: {p: 100 * w + 10 for p in "abc"} for w in (1, 2)}
    out = regret.build(_ctx([trade], pts, kickoff, through=2))
    row = out["trades"][0]
    assert _by_team(row)[1]["total"] == 0.6 and _by_team(row)[1]["cumulative"] == [0.3, 0.6]
    assert row["margin"] == 0.0 and row["leader"] is None  # 0.1 + 0.2 ties 0.3, with no float fuzz
    assert json.loads(json.dumps(out)) == out


def test_missing_points_are_flagged_instead_of_silently_zero():
    trade = _trade(1, 50, 1, _side(1, _p("a"), _p("ghost")), _side(2, _p("b")))
    pts = {1: {"a": 5.0, "b": 2.0}}  # nothing for "ghost" in week 1
    row = regret.build(_ctx([trade], pts, {1: {"a": 110, "b": 110}}, through=1))["trades"][0]
    assert row["gaps"] == 1 and _by_team(row)[1]["total"] == 5.0
    clean = regret.build(_ctx([trade], {1: {"a": 5.0, "b": 2.0, "ghost": 0.0}},
                              {1: {"a": 110, "b": 110}}, through=1))["trades"][0]
    assert "gaps" not in clean


def test_week_with_no_kickoff_times_counts_only_after_the_first_week():
    # Week 1 and 2 have no kickoff data at all. A player with no kickoff entry can't be shown
    # to have played after the trade in its first week, but later weeks come after it.
    trade = _trade(1, 50, 1, _side(1, _p("a")), _side(2, _p("b")))
    pts = {1: {"a": 5.0, "b": 2.0}, 2: {"a": 5.0, "b": 2.0}}
    row = regret.build(_ctx([trade], pts, kicks={}, through=2))["trades"][0]
    one = _by_team(row)[1]["players"][0]
    assert one["weekly"] == [0.0, 5.0] and one["skipped"] == [1]
