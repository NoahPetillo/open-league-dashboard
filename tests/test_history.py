"""League history: past seasons' games, matched by owner id."""

from __future__ import annotations

import logging
from types import SimpleNamespace as NS

from league.history import build, season_games


def _owner(oid: str, first: str) -> dict:
    return {"id": oid, "firstName": first, "displayName": first.lower()}


def _team(tid, oid, first, schedule, scores, outcomes):
    return NS(team_id=tid, owners=[_owner(oid, first)] if oid else [],
              schedule=schedule, scores=scores, outcomes=outcomes)


def _league(reg: int, specs: dict, previous=()):
    """specs: team id → (owner id, first name, [opponent ids], [scores], [outcomes])."""
    teams = {tid: _team(tid, o, n, [], sc, oc) for tid, (o, n, _opp, sc, oc) in specs.items()}
    for tid, (_o, _n, opp, _sc, _oc) in specs.items():
        teams[tid].schedule = [teams[x] if x in teams else x for x in opp]
    return NS(teams=list(teams.values()), settings=NS(reg_season_count=reg),
              previousSeasons=list(previous))


def _season_2025():
    # Week 1: A-B (C on a bye). Week 2: A-C (B on a bye). Week 3, a playoff week: A-B again.
    return _league(2, {
        1: ("{A}", "Ann", [2, 3, 2], [100.0, 90.0, 120.5], ["W", "L", "W"]),
        2: ("{B}", "Bob", [1, 2, 1], [80.0, 0.0, 110.0], ["L", "W", "L"]),
        3: ("{C}", "Cat", [3, 1, 3], [60.0, 95.0, 0.0], ["W", "W", "W"]),
    })


def test_games_listed_once_with_scores_and_playoff_flag():
    games, names = season_games(_season_2025(), 2025)
    by = {(g["week"], g["a"], g["b"]): g for g in games}
    # Byes (a team listed as its own opponent) are not games; each real game appears once.
    assert set(by) == {(1, "{A}", "{B}"), (2, "{A}", "{C}"), (3, "{A}", "{B}")}
    g1 = by[(1, "{A}", "{B}")]
    assert (g1["season"], g1["a_score"], g1["b_score"], g1["playoff"]) == (2025, 100.0, 80.0, False)
    assert (by[(2, "{A}", "{C}")]["a_score"], by[(2, "{A}", "{C}")]["b_score"]) == (90.0, 95.0)
    assert by[(2, "{A}", "{C}")]["playoff"] is False
    assert by[(3, "{A}", "{B}")]["playoff"] is True  # week 3 > 2 regular-season weeks
    assert names == {"{A}": "Ann", "{B}": "Bob", "{C}": "Cat"}


def test_unplayed_games_and_disagreeing_schedules_are_skipped():
    lg = _league(14, {
        1: ("{A}", "Ann", [2, 2], [100.0, 0.0], ["W", "U"]),
        2: ("{B}", "Bob", [1, 1], [80.0, 0.0], ["L", "U"]),
    })
    games, _ = season_games(lg, 2024)
    assert [(g["week"], g["a_score"]) for g in games] == [(1, 100.0)]

    lg = _league(14, {
        1: ("{A}", "Ann", [2], [100.0], ["W"]),
        2: ("{B}", "Bob", [2], [80.0], ["L"]),  # B's schedule doesn't list A for that week
    })
    assert season_games(lg, 2024)[0] == []


def test_ties_and_teams_without_owners():
    lg = _league(14, {
        1: ("{A}", "Ann", [2, 3], [100.0, 90.0], ["T", "W"]),
        2: ("{B}", "Bob", [1, 2], [100.0, 0.0], ["T", "W"]),
        3: (None, "", [3, 1], [60.0, 50.0], ["W", "L"]),  # orphan team (no owner) on a bye, then A
    })
    games, _ = season_games(lg, 2023)
    assert [(g["a"], g["b"], g["a_score"], g["b_score"]) for g in games] == [("{A}", "{B}", 100.0, 100.0)]


def test_empty_previous_seasons_returns_empty_without_loading():
    ctx = NS(lg=NS(previousSeasons=[], teams=[]), client=NS())

    def boom(year):
        raise AssertionError("must not load anything")

    assert build(ctx, load=boom) == {"seasons": [], "games": [], "managers": []}
    # No `previousSeasons` attribute at all is fine too.
    assert build(NS(lg=NS(teams=[]), client=NS()), load=boom)["games"] == []


def test_build_matches_managers_across_seasons_by_owner_id():
    now = _league(14, {
        5: ("{A}", "Ann", [], [], []),      # Ann has a new team id this year
        6: ("{B}", "Robert", [], [], []),   # Bob goes by Robert now
    }, previous=[2024, 2025])
    past = {2024: _league(14, {1: ("{A}", "Ann", [2], [101.0], ["W"]),
                               2: ("{B}", "Bob", [1], [99.0], ["L"])}),
            2025: _season_2025()}
    out = build(NS(lg=now, client=NS()), load=past.__getitem__)
    assert out["seasons"] == [2024, 2025]
    assert [(g["season"], g["week"]) for g in out["games"]][:2] == [(2024, 1), (2025, 1)]
    mgr = {m["key"]: m for m in out["managers"]}
    assert mgr["{A}"] == {"key": "{A}", "name": "Ann", "team": 5}
    assert mgr["{B}"] == {"key": "{B}", "name": "Robert", "team": 6}   # current name wins
    assert mgr["{C}"] == {"key": "{C}", "name": "Cat", "team": None}   # left the league
    assert all(g["a"] in mgr and g["b"] in mgr for g in out["games"])


def test_a_season_that_fails_is_skipped_with_a_warning(caplog):
    now = _league(14, {5: ("{A}", "Ann", [], [], [])}, previous=[2023, 2024])

    def load(year):
        if year == 2023:
            raise RuntimeError("ESPN says no")
        return _league(14, {1: ("{A}", "Ann", [2], [10.0], ["W"]), 2: ("{B}", "Bob", [1], [5.0], ["L"])})

    with caplog.at_level(logging.WARNING):
        out = build(NS(lg=now, client=NS()), load=load)
    assert out["seasons"] == [2024] and len(out["games"]) == 1
    assert "2023" in caplog.text
