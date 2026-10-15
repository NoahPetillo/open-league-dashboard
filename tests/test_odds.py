"""Playoff odds and how they moved week by week."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from league import odds

# 4 teams, two divisions ({1, 2} and {3, 4}), 2 playoff spots, a 6-week regular season.
DIVISIONS = {1: 0, 2: 0, 3: 1, 4: 1}
SCHEDULE = {1: [(1, 2), (3, 4)], 2: [(1, 3), (2, 4)], 3: [(1, 4), (2, 3)],
            4: [(1, 2), (3, 4)], 5: [(1, 3), (2, 4)], 6: [(1, 4), (2, 3)]}


def _game(home, away, hs, as_):
    return {"home": home, "away": away, "home_score": hs, "away_score": as_}


MATCHUPS = {
    1: [_game(1, 2, 150, 120), _game(3, 4, 110, 110)],     # 1 beats 2 (division game); 3-4 tie
    2: [_game(1, 3, 140, 100), _game(2, 4, 130, 90)],      # 1 beats 3, 2 beats 4
    3: [_game(1, 4, 120, 130), _game(2, 3, 105, 115)],     # 4 beats 1, 3 beats 2
    4: [_game(1, 2, 100, 100), _game(3, 4, 90, 95)],       # 1-2 tie (division game)
}


def _ctx(through: int, matchups=None, reg_weeks: int = 6) -> SimpleNamespace:
    return SimpleNamespace(
        teams=[{"id": i} for i in (1, 2, 3, 4)], through=through, reg_weeks=reg_weeks,
        playoff_teams=2, divisions=DIVISIONS, schedule=SCHEDULE,
        matchups={w: g for w, g in (matchups or MATCHUPS).items() if w <= through})


@pytest.fixture(autouse=True)
def _small(monkeypatch):
    monkeypatch.setattr(odds, "MAIN_SIMS", 600)
    monkeypatch.setattr(odds, "HISTORY_SIMS", 300)


def test_standings_count_records_ties_points_and_division_wins():
    st = {s["id"]: s for s in odds._standings([1, 2, 3, 4], MATCHUPS, DIVISIONS, 4)}
    assert (st[1]["wins"], st[1]["losses"], st[1]["ties"]) == (2, 1, 1)
    assert st[3]["ties"] == 1 and st[4]["ties"] == 1 and (st[3]["wins"], st[4]["wins"]) == (1, 2)
    assert st[1]["points_for"] == 150 + 140 + 120 + 100
    assert st[1]["scores"] == [150, 140, 120, 100]
    # Division games: 1-2 (week 1, win for 1; week 4, tie), 3-4 (tie, then a win for 4).
    assert (st[1]["div_wins"], st[2]["div_wins"], st[3]["div_wins"], st[4]["div_wins"]) == (1.5, 0.5, 0.5, 1.5)


def test_standings_only_use_weeks_through_the_cutoff():
    st = {s["id"]: s for s in odds._standings([1, 2, 3, 4], MATCHUPS, DIVISIONS, 1)}
    assert (st[1]["wins"], st[2]["losses"], st[3]["ties"]) == (1, 1, 1)
    assert st[1]["scores"] == [150]


def test_standings_before_week_one_are_blank():
    st = odds._standings([1, 2], {}, DIVISIONS, 0)
    assert all(s["wins"] == s["losses"] == s["ties"] == 0 and s["scores"] == [] for s in st)


def test_build_adds_playoff_odds_and_history_that_ends_on_the_live_numbers():
    out = odds.build(_ctx(through=3))
    live, hist = out["punishment"], out["history"]
    assert live["weeks_left"] == [4, 5, 6] and live["playoff_spots"] == 2
    assert hist["weeks"] == [0, 1, 2, 3]
    assert [t["team"] for t in hist["teams"]] == [1, 2, 3, 4]
    for series, row in zip(hist["teams"], live["teams"], strict=True):
        assert {len(v) for k, v in series.items() if k != "team"} == {4}
        assert series["p_playoffs"][-1] == row["p_playoffs"]
        assert series["p_last"][-1] == row["p_last"]
        assert series["p_division"][-1] == row["p_division"]


def test_history_uses_only_what_was_known_at_the_time():
    hist = odds.build(_ctx(through=3))["history"]
    # Before any games everyone is equal: each team has the same shot at the 2 spots.
    pre = [t["p_playoffs"][0] for t in hist["teams"]]
    assert all(abs(p - 0.5) < 0.12 for p in pre)
    # After week 3 team 1 (2-1) is likelier to make it than team 2 (1-2, same division).
    last = {t["team"]: t["p_playoffs"][-1] for t in hist["teams"]}
    assert last[1] > last[2]
    for k in range(4):
        assert sum(t["p_playoffs"][k] for t in hist["teams"]) == pytest.approx(2, abs=0.02)
        assert sum(t["p_last"][k] for t in hist["teams"]) == pytest.approx(1, abs=0.02)
        assert sum(t["p_division"][k] for t in hist["teams"]) == pytest.approx(2, abs=0.02)


def test_week_zero_history_when_the_season_has_not_started():
    out = odds.build(_ctx(through=0))
    assert out["history"]["weeks"] == [0]
    assert out["punishment"]["weeks_left"] == [1, 2, 3, 4, 5, 6]
    assert all(len(t["p_playoffs"]) == 1 for t in out["history"]["teams"])


def test_finished_season_has_no_race_but_history_ends_on_the_real_outcome():
    matchups = {**MATCHUPS, 5: [_game(1, 3, 100, 90), _game(2, 4, 120, 80)],
                6: [_game(1, 4, 100, 90), _game(2, 3, 120, 80)]}
    out = odds.build(_ctx(through=6, matchups=matchups))
    assert out["punishment"] is None
    hist = out["history"]
    assert hist["weeks"] == list(range(7))
    final = {t["team"]: t for t in hist["teams"]}
    # Everyone's last point is a certainty, and exactly two teams made the playoffs.
    assert all(t["p_playoffs"][-1] in (0, 1) and t["p_last"][-1] in (0, 1) for t in final.values())
    assert sum(t["p_playoffs"][-1] for t in final.values()) == 2
    assert sum(t["p_last"][-1] for t in final.values()) == 1
    assert sum(t["p_division"][-1] for t in final.values()) == 2


def test_playoff_weeks_do_not_count_toward_the_regular_season():
    matchups = {**MATCHUPS, 5: [_game(1, 3, 100, 90), _game(2, 4, 120, 80)],
                6: [_game(1, 4, 100, 90), _game(2, 3, 120, 80)],
                7: [_game(1, 2, 999, 1), _game(3, 4, 999, 1)]}   # a playoff round
    with_playoffs = odds.build(_ctx(through=7, matchups=matchups))["history"]
    without = odds.build(_ctx(through=6, matchups={k: v for k, v in matchups.items() if k <= 6}))["history"]
    assert with_playoffs == without


def test_no_regular_season_length_means_nothing_to_simulate():
    assert odds.build(_ctx(through=2, reg_weeks=0)) == {"punishment": None, "history": None}
