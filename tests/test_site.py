"""Website data: lineup optimizer, trade grading (incl. flipped players), live status."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from league.lineup import best_lineup
from league.live import _status
from league.report import (
    Lineups,
    ReportContext,
    WeekRoster,
    _draft,
    _effective_weeks,
    _grade_side,
    _late_adds,
    _most_traded,
    _parse_trades,
    _team_trade_net,
    _undo,
)

SLOTS = {"RB": 1, "WR": 1, "RB/WR/TE": 1}
ELIG = {
    "rb1": ["RB", "RB/WR/TE", "BE"], "rb2": ["RB", "RB/WR/TE", "BE"],
    "wr1": ["WR", "RB/WR/TE", "BE"], "wr2": ["WR", "RB/WR/TE", "BE"],
    "te1": ["TE", "RB/WR/TE", "BE"],
}


def test_best_lineup_fills_dedicated_slots_before_flex():
    pts = {"rb1": 20, "rb2": 15, "wr1": 5, "wr2": 3, "te1": 10}
    total, starters = best_lineup(pts, ELIG, list(pts), SLOTS)
    # RB takes rb1, WR takes wr1, FLEX takes the best leftover (rb2) — not wr1 stranded.
    assert starters == {"rb1", "wr1", "rb2"}
    assert total == 40


def test_best_lineup_ignores_ineligible_players():
    total, starters = best_lineup({"te1": 30, "wr1": 1}, ELIG, ["te1", "wr1"], {"WR": 1})
    assert starters == {"wr1"} and total == 1


def test_undo_reverses_chained_trades_in_order():
    t1 = {"received": {"a": 0}, "sent": {"x": 0}}   # gave x for a
    t2 = {"received": {"b": 0}, "sent": {"a": 0}}   # then flipped a for b
    assert _undo({"b", "keep"}, [t1, t2]) == {"x", "keep"}


def _side(team, received, sent):
    return {"team": team, "received": {p: p for p in received},
            "sent": {p: p for p in sent}}


def test_trade_grade_follows_a_flip():
    # Team 1 trades rb2 → wr2 (trade 1), then flips wr2 → rb1 (trade 2), both before week 1.
    trades = [{"id": 1, "sides": [_side(1, ["wr2"], ["rb2"]), _side(2, ["rb2"], ["wr2"])]},
              {"id": 2, "sides": [_side(1, ["rb1"], ["wr2"]), _side(3, ["wr2"], ["rb1"])]}]
    rosters = {1: {1: WeekRoster({p: (p, "?") for p in ("rb1", "wr1", "te1")}, set(), 0),
                   2: WeekRoster({"rb2": ("rb2", "RB")}, set(), 0),
                   3: WeekRoster({"wr2": ("wr2", "WR")}, set(), 0)}}
    lu = Lineups({1: {"rb1": 20, "rb2": 15, "wr1": 5, "wr2": 3, "te1": 10}}, ELIG, SLOTS)
    effs = _effective_weeks(trades, rosters, [1])
    assert effs == [1, 1]  # trade 1's player was flipped before week 1, so it inherits week 1

    first = _grade_side(0, trades[0]["sides"][0], trades, effs, rosters, lu, {}, [1])
    # Actual {rb1, wr1, te1} = 20+5+10 = 35; without either trade {rb2, wr1, te1} = 15+5+10 = 30.
    assert first["net"] == 5 and first["flipped_into"] == [2]
    assert first["received"][0]["weeks_rostered"] == 0  # wr2 never played for team 1
    assert _team_trade_net(1, trades, effs, rosters, lu, [1]) == 5


def test_trade_after_last_box_score_is_pending():
    trades = [{"id": 1, "sides": [_side(1, ["rb1"], ["rb2"]), _side(2, ["rb2"], ["rb1"])]}]
    rosters = {1: {1: WeekRoster({"rb2": ("rb2", "RB")}, set(), 0),
                   2: WeekRoster({"rb1": ("rb1", "RB")}, set(), 0)}}
    assert _effective_weeks(trades, rosters, [1]) == [None]


def test_most_traded_ranks_by_trades_then_teams_then_points():
    # a: 1 → 2 → 3 (2 trades, 3 teams). b: 1 → 2 → 1 (2 trades, 2 teams). c: once.
    trades = [{"date": 1, "sides": [_side(1, ["x"], ["a", "b"]), _side(2, ["a", "b"], ["x"])]},
              {"date": 2, "sides": [_side(2, ["c"], ["a"]), _side(3, ["a"], ["c"])]},
              {"date": 3, "sides": [_side(2, ["y"], ["b"]), _side(1, ["b"], ["y"])]}]
    pts = {1: {"a": 10, "b": 30}, 2: {"a": 0, "b": 20}}
    top = _most_traded(trades, pts, {"a": "WR"}, {"a": "KC"}, [1, 2])
    assert [p["id"] for p in top[:2]] == ["a", "b"]
    a = top[0]
    assert a["trades"] == 2 and a["path"] == [1, 2, 3] and a["teams"] == 3 and a["owner"] == 3
    assert a["season_points"] == 10 and a["avg"] == 10 and a["pro_team"] == "KC"
    assert top[1]["path"] == [1, 2, 1] and top[1]["teams"] == 2


def test_parse_trades_keeps_faab_with_its_trade():
    activity = [{"date": 5, "moves": [(5, "TRADE_SENT", "p1", 0), (3, "TRADE_RECEIVED", "p1", 0),
                                      (3, "TRADE_SENT", "p2", 0), (5, "TRADE_RECEIVED", "p2", 0),
                                      (5, "FAAB_SENT", "", 10), (3, "FAAB_RECEIVED", "", 10)]},
                {"date": 6, "moves": [(1, "WAIVER ADDED", "p9", 4)]}]
    (trade,) = _parse_trades(activity, lambda pid: pid.upper())
    sides = {s["team"]: s for s in trade["sides"]}
    assert sides[3]["received"] == {"p1": "P1"} and sides[3]["faab_received"] == 10
    assert sides[5]["sent"] == {"p1": "P1"} and sides[5]["faab_sent"] == 10
    assert sides[5]["faab_received"] == 0 and sides[3]["faab_sent"] == 0


def test_live_status_from_kickoff():
    now = datetime(2026, 10, 4, 15, 0)
    bp = lambda kick: SimpleNamespace(on_bye_week=False, game_date=kick, game_played=0)  # noqa: E731
    assert _status(bp(now + timedelta(hours=1)), now) == "upcoming"
    assert _status(bp(now - timedelta(hours=1)), now) == "live"
    assert _status(bp(now - timedelta(hours=4)), now) == "final"
    assert _status(SimpleNamespace(on_bye_week=True), now) == "bye"


DAY = 24 * 3600 * 1000


def test_late_adds_need_an_add_after_kickoff_by_a_team_that_lacked_him():
    rosters = {1: {1: WeekRoster({p: (p, "RB") for p in ("early", "late", "back", "kept")}, set(), 0)}}
    kick = 10 * DAY
    kickoff = {1: {"early": kick, "late": kick, "back": kick, "kept": kick}}
    activity = [{"date": kick - DAY, "moves": [(1, "FA ADDED", "early", 0)]},      # added before his game
                {"date": kick + 3600, "moves": [(1, "WAIVER ADDED", "late", 3)]},  # added after it
                {"date": kick - 2 * DAY, "moves": [(1, "DROPPED", "back", 0)]},    # cut, then re-added late
                {"date": kick + 7200, "moves": [(1, "FA ADDED", "back", 0)]},
                {"date": kick + 7200, "moves": [(1, "DROPPED", "kept", 0)]}]       # cut after playing
    draft = [{"pick": 1, "round": 1, "round_pick": 1, "team": 1, "id": "back", "name": "Back"},
             {"pick": 2, "round": 1, "round_pick": 2, "team": 1, "id": "kept", "name": "Kept"}]
    assert _late_adds(rosters, kickoff, activity, draft) == {1: {1: {"late", "back"}}}


def test_startable_drops_late_adds_only():
    roster = WeekRoster({"a": ("A", "RB"), "b": ("B", "WR")}, {"a"}, 10)
    ctx = ReportContext(client=None, lg=None, season=2026, through=1, current_week=2, weeks=[1],
                        reg_weeks=14, playoff_teams=6, rosters={1: {7: roster}}, pts={}, pos={}, pro={},
                        names={}, lu=None, matchups={}, schedule={}, divisions={}, division_names={},
                        kicks={}, activity=[], trades=[], teams=[], faab_budget=100,
                        late={1: {7: {"b"}}})
    assert ctx.startable(1, 7) == {"a"}
    assert ctx.startable(1, 8) == set() and ctx.startable(2, 7) == set()


def test_draft_reads_picks_in_order():
    pick = lambda r, p, team, pid: SimpleNamespace(round_num=r, round_pick=p, team=SimpleNamespace(team_id=team),  # noqa: E731
                                                   playerId=pid, playerName=f"P{pid}")
    lg = SimpleNamespace(draft=[pick(2, 1, 2, 30), pick(1, 2, 1, 20), pick(1, 1, 2, 10)])
    assert [(p["pick"], p["team"], p["id"]) for p in _draft(lg)] == [(1, 2, "10"), (2, 1, "20"), (3, 2, "30")]
