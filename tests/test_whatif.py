"""What-if lineups: flips, non-flips, ties, late adds, swap lists and record math on a tiny fake league."""

from __future__ import annotations

import json
from types import SimpleNamespace

from league import whatif
from league.report import Lineups, WeekRoster

SLOTS = {"QB": 1, "RB": 1, "WR": 1}
POS = {"qb": "QB", "rb": "RB", "wr": "WR"}


def _pos(pid: str) -> str:
    return POS[pid.rstrip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")]


def _ctx(weeks: dict[int, tuple[dict, list[tuple[int, int]]]], late=None, reg_weeks=14, startable=True):
    """``weeks[w] = ({team: (started, bench[, score])}, [(home, away), ...])`` where started and
    bench are {player id: points}. A team's score is the sum of its starters unless one is given.
    ``late[w][team]`` = players that team only picked up after their game kicked off."""
    late = late or {}
    rosters, pts, matchups = {}, {}, {}
    for w, (spec, games) in weeks.items():
        rosters[w], pts[w] = {}, {}
        for team, (started, bench, *score) in spec.items():
            players = {pid: (f"Player {pid}", _pos(pid)) for pid in {**started, **bench}}
            rosters[w][team] = WeekRoster(players, set(started), score[0] if score else sum(started.values()))
            pts[w].update({**started, **bench})
        matchups[w] = [{"home": h, "away": a, "home_score": rosters[w][h].score,
                        "away_score": rosters[w][a].score} for h, a in games]
    eligible = {pid: [_pos(pid), "BE"] for week in pts.values() for pid in week}
    ctx = SimpleNamespace(
        weeks=sorted(weeks), rosters=rosters, pts=pts, matchups=matchups, reg_weeks=reg_weeks,
        pos={pid: _pos(pid) for pid in eligible}, names={pid: f"Player {pid}" for pid in eligible},
        lu=Lineups(pts, eligible, SLOTS))
    if startable:
        ctx.startable = lambda w, t: set(rosters[w][t].players) - late.get(w, {}).get(t, set())
    return ctx


def _main():
    week1 = ({
        # 1 lost 30-40 but rb2 (25) on the bench would have made it 45: a flip.
        1: ({"qb1": 10, "rb1": 10, "wr1": 10}, {"rb2": 25, "wr2": 4}),
        2: ({"qb2": 15, "rb3": 15, "wr3": 10}, {}),
        # 3 lost 20-25 and its best lineup is only 24: a loss either way.
        3: ({"qb3": 5, "rb4": 5, "wr4": 10}, {"wr5": 14}),
        4: ({"qb4": 10, "rb5": 10, "wr6": 5}, {}),
        # 5 lost 20-30 and its best lineup is exactly 30: a tie, not a flip.
        5: ({"qb5": 10, "rb6": 5, "wr7": 5}, {"rb7": 15}),
        6: ({"qb6": 10, "rb8": 10, "wr8": 10}, {}),
    }, [(1, 2), (3, 4), (5, 6)])
    week2 = ({
        1: ({"qb1": 20, "rb1": 20, "wr1": 10}, {"rb2": 3}),
        2: ({"qb2": 15, "rb3": 15, "wr3": 10}, {}),
        # 3 lost 20-25 again, but wrL (50) was picked up after his game: it can't be the flip.
        3: ({"qb3": 5, "rb4": 5, "wr4": 10}, {"wr5": 14, "wrL": 50}),
        4: ({"qb4": 10, "rb5": 10, "wr6": 5}, {}),
        # 5 tied 30-30, and wr9 (12) turns that tie into a win in the best record; still no flip.
        5: ({"qb5": 10, "rb6": 10, "wr7": 10}, {"wr9": 12}),
        6: ({"qb6": 10, "rb8": 10, "wr8": 10}, {}),
    }, [(1, 2), (3, 4), (5, 6)])
    return _ctx({1: week1, 2: week2}, late={2: {3: {"wrL"}}})


def _team(out: dict, team: int) -> dict:
    return next(t for t in out["teams"] if t["team"] == team)


def _game(out: dict, week: int, home: int) -> dict:
    return next(g for x in out["weeks"] if x["week"] == week for g in x["games"] if g["home"] == home)


def test_flip_when_best_lineup_beats_the_score_that_won():
    out = whatif.build(_main())
    g = _game(out, 1, 1)
    assert (g["home_score"], g["away_score"], g["home_best"], g["away_best"]) == (30, 40, 45, 40)
    assert g["flipped"] == 1
    (flip,) = _team(out, 1)["flips"]
    assert (flip["week"], flip["opp"], flip["score"], flip["best"], flip["opp_score"]) == (1, 2, 30, 45, 40)
    assert out["flips_total"] == 1


def test_loss_that_the_best_lineup_still_loses_is_not_a_flip():
    out = whatif.build(_main())
    g = _game(out, 1, 3)
    assert (g["home_best"], g["away_best"], g["flipped"]) == (24, 25, None)
    assert _team(out, 3)["flips"] == []


def test_best_lineup_equal_to_the_opponent_is_a_tie_not_a_flip():
    out = whatif.build(_main())
    g = _game(out, 1, 5)
    assert (g["home_score"], g["home_best"], g["away_score"]) == (20, 30, 30)
    assert g["flipped"] is None and _team(out, 5)["flips"] == []
    assert g["both_best_winner"] is None  # both best lineups are 30: dead even


def test_late_pickup_is_never_part_of_the_best_lineup():
    out = whatif.build(_main())
    g = _game(out, 2, 3)
    # With wrL it would be 5 + 5 + 50 = 60 and a flip; without him the best is 5 + 5 + 14 = 24.
    assert (g["home_best"], g["flipped"]) == (24, None)
    assert _team(out, 3)["flips"] == []
    # Without a startable() to ask, the whole roster counts: the late pickup creates a "flip".
    ctx = _main()
    del ctx.startable
    assert _game(whatif.build(ctx), 2, 3)["flipped"] == 3


def test_swap_lists_name_who_comes_in_and_who_goes_out():
    (flip,) = _team(whatif.build(_main()), 1)["flips"]
    assert flip["swap_in"] == [{"id": "rb2", "name": "Player rb2", "pos": "RB", "points": 25}]
    assert flip["swap_out"] == [{"id": "rb1", "name": "Player rb1", "pos": "RB", "points": 10}]


def test_record_math_actual_and_best():
    out = whatif.build(_main())
    rec = lambda t: tuple(t[k] for k in ("wins", "losses", "ties", "best_wins", "best_losses", "best_ties"))  # noqa: E731
    # Each opponent keeps its actual score; a team that really won still wins.
    assert rec(_team(out, 1)) == (1, 1, 0, 2, 0, 0)
    assert rec(_team(out, 2)) == (1, 1, 0, 1, 1, 0)
    assert rec(_team(out, 3)) == (0, 2, 0, 0, 2, 0)
    assert rec(_team(out, 4)) == (2, 0, 0, 2, 0, 0)
    # Team 5: lost, then tied 30-30. Best lineups: a tie (30 vs 30), then a win (32 vs 30).
    assert rec(_team(out, 5)) == (0, 1, 1, 1, 0, 1)
    assert rec(_team(out, 6)) == (1, 0, 1, 1, 0, 1)
    assert _team(out, 5)["flips"] == []  # a tie turned into a win is not a flip: nobody lost


def test_points_left_is_best_minus_score_over_the_games():
    out = whatif.build(_main())
    assert [_team(out, t)["points_left"] for t in range(1, 7)] == [15, 0, 8, 0, 12, 0]


def test_both_best_lineups_pick_a_winner_by_best_score():
    out = whatif.build(_main())
    assert [_game(out, 1, h)["both_best_winner"] for h in (1, 3, 5)] == [1, 4, None]
    assert [_game(out, 2, h)["both_best_winner"] for h in (1, 3, 5)] == [1, 4, 5]


def test_output_shape_is_json_and_compact():
    out = whatif.build(_main())
    assert json.loads(json.dumps(out)) == out
    assert [w["week"] for w in out["weeks"]] == [1, 2]
    assert set(out) == {"weeks", "teams", "flips_total"}
    assert set(out["weeks"][0]["games"][0]) == {
        "home", "away", "home_score", "away_score", "home_best", "away_best", "flipped", "both_best_winner"}
    assert set(_team(out, 1)) == {
        "team", "wins", "losses", "ties", "best_wins", "best_losses", "best_ties", "points_left", "flips"}
    assert set(_team(out, 1)["flips"][0]) == {
        "week", "opp", "score", "best", "opp_score", "swap_in", "swap_out"}
    assert [t["team"] for t in out["teams"]] == [1, 2, 3, 4, 5, 6]


def _solo(started, bench, opp_score, score=None, **kw):
    """Team 1 against a team 2 that scored ``opp_score`` with nothing on its bench."""
    mine = (started, bench, *([] if score is None else [score]))
    them = ({"qb9": opp_score}, {})
    return _ctx({1: ({1: mine, 2: them}, [(1, 2)])}, **kw)


def test_swap_lists_are_sorted_by_points_high_to_low():
    ctx = _solo({"qb1": 2, "rb1": 3, "wr1": 1}, {"qb2": 20, "rb2": 8, "wr2": 14}, opp_score=40)
    (flip,) = _team(whatif.build(ctx), 1)["flips"]
    assert flip["best"] == 42 and flip["score"] == 6
    assert [p["id"] for p in flip["swap_in"]] == ["qb2", "wr2", "rb2"]
    assert [p["points"] for p in flip["swap_in"]] == [20, 14, 8]
    assert [p["id"] for p in flip["swap_out"]] == ["rb1", "qb1", "wr1"]
    assert [p["pos"] for p in flip["swap_out"]] == ["RB", "QB", "WR"]


def test_equal_scorers_never_swap_the_real_starter_out():
    # wr9 started and wr1 sat, both for 5: only the QB change is a real swap, whatever the id order.
    ctx = _solo({"qb1": 0, "rb1": 5, "wr9": 5}, {"qb2": 20, "wr1": 5}, opp_score=24)
    (flip,) = _team(whatif.build(ctx), 1)["flips"]
    assert flip["best"] == 30
    assert [p["id"] for p in flip["swap_in"]] == ["qb2"]
    assert [p["id"] for p in flip["swap_out"]] == ["qb1"]


def test_best_never_reads_below_the_score():
    # ESPN says 35 although the starters add up to 30 and nobody on the bench helps: best stays 35.
    ctx = _solo({"qb1": 10, "rb1": 10, "wr1": 10}, {"wr2": 2}, opp_score=36, score=35)
    out = whatif.build(ctx)
    assert _game(out, 1, 1)["home_best"] == 35 and out["flips_total"] == 0
    assert _team(out, 1)["points_left"] == 0 and _team(out, 1)["flips"] == []


def test_no_flip_from_rounding_when_the_best_lineup_is_the_lineup_started():
    # The starters add up to 30.00 but ESPN's total is 29.98; the best lineup IS the lineup started,
    # so best stays 29.98 and does not leapfrog the opponent's 29.99.
    ctx = _solo({"qb1": 10, "rb1": 10, "wr1": 10}, {"wr2": 2}, opp_score=29.99, score=29.98)
    out = whatif.build(ctx)
    assert _game(out, 1, 1)["home_best"] == 29.98 and _game(out, 1, 1)["flipped"] is None
    assert (_team(out, 1)["best_wins"], _team(out, 1)["best_losses"]) == (0, 1)


def test_best_is_rounded_to_two_places():
    ctx = _solo({"qb1": 0.1, "rb1": 0.2, "wr1": 0.0}, {"wr2": 10.15}, opp_score=5)
    assert _game(whatif.build(ctx), 1, 1)["home_best"] == 10.45


def test_an_empty_lineup_slot_gets_filled_from_the_bench():
    ctx = _solo({"qb1": 10, "rb1": 10}, {"wr1": 7}, opp_score=25)  # nobody was started at WR
    (flip,) = _team(whatif.build(ctx), 1)["flips"]
    assert (flip["score"], flip["best"]) == (20, 27)
    assert [p["id"] for p in flip["swap_in"]] == ["wr1"] and flip["swap_out"] == []


def test_games_after_the_regular_season_are_flagged_and_stay_out_of_the_record():
    lost = lambda: ({1: ({"qb1": 10, "rb1": 10, "wr1": 10}, {"rb2": 25}), 2: ({"qb9": 40}, {})}, [(1, 2)])  # noqa: E731
    ctx = _ctx({1: lost(), 2: lost()}, reg_weeks=1)
    out = whatif.build(ctx)
    assert "playoff" not in _game(out, 1, 1) and _game(out, 2, 1)["playoff"] is True
    t = _team(out, 1)
    assert (t["wins"], t["losses"], t["best_wins"], t["best_losses"], t["points_left"]) == (0, 1, 1, 0, 15)
    assert [(f["week"], f.get("playoff")) for f in t["flips"]] == [(1, None), (2, True)]
    assert out["flips_total"] == 2
    # With no regular-season length known, every week counts.
    out = whatif.build(_ctx({1: lost(), 2: lost()}, reg_weeks=0))
    assert (_team(out, 1)["losses"], _team(out, 1)["points_left"]) == (2, 30)
    assert "playoff" not in _game(out, 2, 1)


def test_nothing_to_show_before_a_game_is_played():
    assert whatif.build(_ctx({})) is None
    assert whatif.build(_ctx({1: ({}, [])})) is None
