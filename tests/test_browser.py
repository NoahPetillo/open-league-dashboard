"""The browser entry point's own logic: turning espn-api teams into games and standings,
and routing requests (straight to ESPN, or through the relay when there are cookies)."""

from __future__ import annotations

from types import SimpleNamespace

import browser


def _team(tid, opponents, scores, **kw):
    t = SimpleNamespace(team_id=tid, team_name=f"T{tid}", team_abbrev=f"T{tid}", owners=[{"firstName": f"M{tid}"}],
                        wins=0, losses=0, ties=0, points_for=sum(scores), points_against=0.0,
                        streak_type="WIN", streak_length=0, standing=None, logo_url="", scores=scores)
    t._opponents = opponents
    t.__dict__.update(kw)
    return t


def _league(teams):
    by_id = {t.team_id: t for t in teams}
    for t in teams:
        t.schedule = [by_id[o] for o in t._opponents]
    return SimpleNamespace(teams=teams)


def test_matchups_lists_each_game_once():
    lg = _league([_team(1, [2, 3], [100, 90]), _team(2, [1, 4], [80, 70]),
                  _team(3, [4, 1], [60, 95]), _team(4, [3, 2], [110, 75])])
    games = browser._matchups(lg, 2)
    assert games[1] == [{"home": 1, "away": 2, "home_score": 100, "away_score": 80},
                        {"home": 3, "away": 4, "home_score": 60, "away_score": 110}]
    assert games[2] == [{"home": 1, "away": 3, "home_score": 90, "away_score": 95},
                        {"home": 2, "away": 4, "home_score": 70, "away_score": 75}]


def test_matchups_skips_byes():
    lg = _league([_team(1, [1], [100]), _team(2, [2], [80])])  # a team scheduled against itself
    assert browser._matchups(lg, 1) == {1: []}


def test_standings_all_play():
    lg = _league([_team(1, [2], [100]), _team(2, [1], [80]), _team(3, [4], [90]), _team(4, [3], [90])])
    rows = {r["id"]: r for r in browser._standings(lg, browser._matchups(lg, 1))}
    assert (rows[1]["allplay_w"], rows[1]["allplay_l"]) == (3, 0)
    assert (rows[2]["allplay_w"], rows[2]["allplay_l"]) == (0, 3)
    assert (rows[3]["allplay_w"], rows[3]["allplay_l"]) == (1, 1)  # the tie with team 4 counts as neither
    assert rows[1]["manager"] == "M1"


def test_braced_swid():
    assert browser._braced("ABC-123") == "{ABC-123}"
    assert browser._braced(" {ABC-123} ") == "{ABC-123}"
    assert browser._braced("") is None and browser._braced(None) is None


def test_requests_with_cookies_go_through_the_relay(monkeypatch):
    seen = {}
    http = browser._Http("https://example.test/api/espn/")
    monkeypatch.setattr(http.session, "get", lambda url, **kw: seen.update(url=url, **kw))
    http.get(browser.ESPN + "seasons/2026/segments/0/leagues/1", params={"view": "mTeam"},
             cookies={"espn_s2": "s2", "SWID": "{id}"})
    assert seen["url"] == "https://example.test/api/espn/seasons/2026/segments/0/leagues/1"
    assert seen["headers"] == {"x-espn-s2": "s2", "x-espn-swid": "{id}"}
    assert "cookies" not in seen


def test_requests_without_cookies_go_straight_to_espn(monkeypatch):
    seen = {}
    http = browser._Http("https://example.test/api/espn/")
    monkeypatch.setattr(http.session, "get", lambda url, **kw: seen.update(url=url, **kw))
    http.get(browser.ESPN + "seasons/2026/players", headers={"x-fantasy-filter": "{}"}, cookies=None)
    assert seen["url"] == browser.ESPN + "seasons/2026/players"
    assert seen["headers"] == {"x-fantasy-filter": "{}"}
