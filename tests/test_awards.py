"""Weekly awards: each award on a tiny fake league, plus ties, byes and season tallies."""

from __future__ import annotations

import json
from types import SimpleNamespace

from league import awards
from league.report import Lineups, WeekRoster

SLOTS = {"RB": 1, "WR": 1, "K": 1, "D/ST": 1, "HC": 1}
POS = {"rb": "RB", "wr": "WR", "k": "K", "dst": "D/ST", "hc": "HC"}


def _pos(pid: str) -> str:
    return POS[pid.rstrip("0123456789")]


def _roster(started: dict[str, float], bench: dict[str, float], score: float):
    """Roster + points from {player id: points}; ids look like 'rb1', 'wr3', 'k2', 'dst3'."""
    players = {pid: (f"Player {pid}", _pos(pid)) for pid in {**started, **bench}}
    return WeekRoster(players, set(started), score), {**started, **bench}


def _ctx():
    rosters = {
        1: {
            1: _roster({"rb1": 20, "wr1": 10, "k1": 8}, {"rb2": 25}, 38),
            2: _roster({"rb3": 4, "wr3": 2, "k2": 0}, {"wr4": 30, "rb4": 3}, 6),
            3: _roster({"rb5": 11, "wr5": 7, "k3": 6, "dst3": -1}, {}, 23),
            4: _roster({"rb6": 17, "wr6": 7, "k4": 6, "hc4": -5}, {}, 25),
            5: _roster({"rb7": 0}, {}, 0),  # on a bye: a roster, but no matchup
        },
        2: {
            1: _roster({"rb1": 50}, {}, 50),
            2: _roster({"rb3": 50}, {}, 50),
            3: _roster({"rb5": 50}, {}, 50),
            4: _roster({"rb6": 40}, {}, 40),
        },
    }
    pts = {w: {pid: p for _r, pp in teams.values() for pid, p in pp.items()} for w, teams in rosters.items()}
    rosters = {w: {t: r for t, (r, _p) in teams.items()} for w, teams in rosters.items()}
    eligible = {pid: [_pos(pid), "BE"] for week in pts.values() for pid in week}
    names = {pid: f"Player {pid}" for pid in eligible}
    return SimpleNamespace(
        weeks=[1, 2, 3],
        rosters=rosters, pts=pts, pos={pid: _pos(pid) for pid in eligible},
        pro={"rb1": "KC", "wr4": "NYJ"}, names=names,
        lu=Lineups(pts, eligible, SLOTS),
        matchups={
            1: [{"home": 1, "away": 2, "home_score": 38, "away_score": 6},
                {"home": 3, "away": 4, "home_score": 23, "away_score": 25}],
            2: [{"home": 1, "away": 2, "home_score": 50, "away_score": 50},
                {"home": 3, "away": 4, "home_score": 50, "away_score": 40}],
            3: [],
        },
        teams=[{"id": 1, "name": "Alpha", "manager": "Jordan"},
               {"id": 2, "name": "Bravo", "manager": "Morgan"},
               {"id": 3, "name": "Charlie", "manager": "Chris"},
               {"id": 4, "name": "Delta", "manager": ""},
               {"id": 5, "name": "Echo", "manager": "Eli"}],
    )


def _week(out: dict, w: int) -> dict[str, dict]:
    return {a["key"]: a for a in next(x for x in out["weeks"] if x["week"] == w)["awards"]}


def test_team_awards_week_one():
    a = _week(awards.build(_ctx()), 1)
    assert (a["top_dog"]["team"], a["top_dog"]["value"], a["top_dog"]["opponent"]) == (1, 38, 2)
    assert a["top_dog"]["detail"] == "38.0 vs Morgan's 6.0"
    assert (a["toilet_bowl"]["team"], a["toilet_bowl"]["value"]) == (2, 6)
    assert (a["blowout"]["team"], a["blowout"]["value"], a["blowout"]["opponent"]) == (1, 32, 2)
    assert a["blowout"]["detail"] == "Won 38.0 to Morgan's 6.0"
    # Closest win: team 4 over team 3 by 2. A manager-less team falls back to its name.
    assert (a["nail_biter"]["team"], a["nail_biter"]["value"], a["nail_biter"]["opponent"]) == (4, 2, 3)
    assert a["nail_biter"]["detail"] == "Won 25.00 to Chris' 23.00"
    # Best score in a loss (team 3's 23, beating team 2's 6); lowest score in a win (team 4's 25).
    assert (a["robbed"]["team"], a["robbed"]["value"]) == (3, 23)
    assert a["robbed"]["detail"] == "Lost 23.0 to Delta's 25.0"
    assert (a["stole_one"]["team"], a["stole_one"]["value"]) == (4, 25)


def test_bench_warmer_is_best_lineup_minus_score():
    a = _week(awards.build(_ctx()), 1)["bench_warmer"]
    # Team 2 scored 6 but {rb3 4, wr4 30, k2 0} was 34 → 28 left on the bench. Team 1 left 5.
    assert (a["team"], a["value"], a["opponent"]) == (2, 28, 1)
    assert a["detail"] == "Scored 6.0; the best lineup was 34.0"
    assert a["player"] is None


def test_player_awards_week_one():
    a = _week(awards.build(_ctx()), 1)
    assert (a["mvp"]["team"], a["mvp"]["value"]) == (1, 20)
    assert a["mvp"]["player"] == {"id": "rb1", "name": "Player rb1", "pos": "RB", "pro_team": "KC"}
    assert a["mvp"]["detail"] == "Player rb1 (RB, KC)"
    # Kickers (0 pts), defenses (-1) and head coaches (-5) never count as duds; neither does the bye team's 0.
    assert (a["dud"]["team"], a["dud"]["value"], a["dud"]["player"]["id"]) == (2, 2, "wr3")
    assert a["dud"]["detail"] == "Started Player wr3 (WR) for 2.0"
    assert a["dud"]["tied"] == 0


def test_bench_blunder_needs_a_legal_swap():
    a = _week(awards.build(_ctx()), 1)["bench_blunder"]
    # Team 2 benched wr4 (30) for wr3 (2) = 28; its benched rb4 (3) didn't beat starter rb3 (4).
    # Team 1's benched rb2 (25) over rb1 (20) is only 5.
    assert (a["team"], a["value"], a["player"]["id"], a["opponent"]) == (2, 28, "wr4", 1)
    assert a["player"]["pro_team"] == "NYJ"
    assert a["detail"] == "Benched Player wr4 (30.0) for Player wr3 (2.0)"


def test_bench_blunder_can_cross_positions_through_the_flex():
    # A benched TE (28.1) could have taken the FLEX spot of a WR who scored 3.1.
    slots = {"WR": 1, "TE": 1, "RB/WR/TE": 1}
    elig = {"wr1": ["WR", "RB/WR/TE", "BE"], "wr2": ["WR", "RB/WR/TE", "BE"],
            "te1": ["TE", "RB/WR/TE", "BE"], "te2": ["TE", "RB/WR/TE", "BE"],
            "x1": ["WR", "RB/WR/TE", "BE"], "x2": ["WR", "RB/WR/TE", "BE"], "x3": ["TE", "BE"]}
    pts = {1: {"wr1": 20, "wr2": 3.1, "te1": 10, "te2": 28.1, "x1": 9, "x2": 9, "x3": 9}}
    pos = {"wr1": "WR", "wr2": "WR", "te1": "TE", "te2": "TE", "x1": "WR", "x2": "WR", "x3": "TE"}
    players = lambda ids: {i: (i, pos[i]) for i in ids}  # noqa: E731
    ctx = SimpleNamespace(
        weeks=[1], pos=pos, pro={}, names={i: i for i in pos}, lu=Lineups(pts, elig, slots),
        rosters={1: {1: WeekRoster(players(["wr1", "wr2", "te1", "te2"]), {"wr1", "wr2", "te1"}, 33.1),
                     2: WeekRoster(players(["x1", "x2", "x3"]), {"x1", "x2", "x3"}, 27)}},
        pts=pts, matchups={1: [{"home": 1, "away": 2, "home_score": 33.1, "away_score": 27}]},
        teams=[{"id": 1, "name": "A", "manager": "Pat"}, {"id": 2, "name": "B", "manager": "Taylor"}])
    a = _week(awards.build(ctx), 1)["bench_blunder"]
    assert (a["team"], a["value"], a["player"]["id"]) == (1, 25, "te2")
    assert a["detail"] == "Benched te2 (28.1) for wr2 (3.1)"


def test_ties_are_not_awards_and_exact_ties_are_flagged():
    a = _week(awards.build(_ctx()), 2)
    # Team 1 and 2 tied 50-50: nobody is "robbed" by it and it's nobody's blowout.
    assert a["blowout"]["team"] == 3 and a["nail_biter"]["team"] == 3
    assert a["robbed"]["team"] == 4 and a["stole_one"]["team"] == 3
    # Three teams hit 50: lowest team id gets top dog, and the other two are counted.
    assert (a["top_dog"]["team"], a["top_dog"]["tied"]) == (1, 2)
    assert (a["mvp"]["team"], a["mvp"]["tied"]) == (1, 2)
    assert a["toilet_bowl"]["team"] == 4 and a["toilet_bowl"]["tied"] == 0
    # Best lineup equals the score everywhere, and no one benched anyone: no award.
    assert "bench_warmer" not in a and "bench_blunder" not in a


def test_dud_ties_go_to_the_lower_scoring_team():
    ctx = _ctx()
    # Week 2: two started players score 0 — team 1's (team score 50) and team 4's (40).
    ctx.pts[2]["rb1"] = 0
    ctx.pts[2]["rb6"] = 0
    d = _week(awards.build(ctx), 2)["dud"]
    assert (d["team"], d["value"], d["tied"]) == (4, 0, 1)


def test_week_without_games_is_skipped_and_bye_teams_get_nothing():
    out = awards.build(_ctx())
    assert [w["week"] for w in out["weeks"]] == [1, 2]
    assert all(x["team"] != 5 for w in out["weeks"] for x in w["awards"])


def test_season_counts_every_team_with_zeros():
    out = awards.build(_ctx())
    season = {s["team"]: s["counts"] for s in out["season"]}
    assert sorted(season) == [1, 2, 3, 4, 5]
    assert all(set(c) == set(awards.TITLES) for c in season.values())
    assert season[1]["top_dog"] == 2 and season[1]["blowout"] == 1 and season[1]["mvp"] == 2
    assert season[2]["toilet_bowl"] == 1 and season[2]["bench_warmer"] == 1
    assert season[5] == dict.fromkeys(awards.TITLES, 0)
    total = sum(sum(c.values()) for c in season.values())
    assert total == sum(len(w["awards"]) for w in out["weeks"])


def test_output_is_json_and_in_award_order():
    out = awards.build(_ctx())
    json.dumps(out)
    keys = [x["key"] for x in out["weeks"][0]["awards"]]
    assert keys == [k for k in awards.TITLES if k in keys]
    for x in out["weeks"][0]["awards"]:
        assert set(x) == {"key", "title", "team", "value", "detail", "opponent", "player", "tied"}
        assert x["title"] == awards.TITLES[x["key"]]


def test_no_completed_weeks_gives_an_empty_report():
    ctx = _ctx()
    ctx.weeks = []
    out = awards.build(ctx)
    assert out["weeks"] == [] and len(out["season"]) == 5
