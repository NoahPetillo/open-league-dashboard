"""Waiver drop regret: the window, which weeks count, who held him, who got the points."""

from __future__ import annotations

from types import SimpleNamespace

from league import drops
from league.report import WeekRoster

DAY = 86_400_000
# Three weeks; kickoffs Thursday night (first) to Monday night (last).
KICKS = {1: (1 * DAY, 5 * DAY), 2: (8 * DAY, 12 * DAY), 3: (15 * DAY, 19 * DAY)}


def _row(date, *moves):
    return {"date": date, "moves": list(moves)}


def _roster(*players, started=()):
    return WeekRoster({p: (p.title(), "WR") for p in players}, set(started), 0.0)


def _ctx(activity, *, rosters=None, pts=None, kickoff=None, pos=None, pro=None, late=None, now=None,
         weeks=(1, 2, 3)):
    """A context with three teams. ``now`` maps player id → the team holding him today."""
    now = now or {}
    lg = SimpleNamespace(teams=[
        SimpleNamespace(team_id=t, roster=[SimpleNamespace(playerId=int(p)) for p, owner in now.items() if owner == t])
        for t in (1, 2, 3)])
    return SimpleNamespace(
        activity=activity, rosters=rosters or {}, pts=pts or {}, kickoff=kickoff or {}, kicks=KICKS,
        weeks=list(weeks), through=max(weeks), late=late or {}, lg=lg,
        names={"1": "Alpha", "2": "Bravo", "3": "Charlie", "9": "Kicker"},
        pos={"1": "WR", "2": "RB", "3": "QB", "9": "K", **(pos or {})},
        pro={"1": "KC", "2": "KC", "3": "BUF", **(pro or {})},
        teams=[{"id": 1}, {"id": 2}, {"id": 3}])


def _only(out):
    assert len(out["drops"]) == 1
    return out["drops"][0]


# ── who got the points ─────────────────────────────────────────────────────────
def test_dropped_player_scores_for_another_team_and_the_free_agent_weeks_count_too():
    act = [_row(0, (1, "DROPPED", "1", 0)),
           _row(6 * DAY, (2, "FA ADDED", "1", 0))]
    rosters = {2: {2: _roster("1", started=["1"])}, 3: {2: _roster("1")}}   # started in week 2, benched in week 3
    kickoff = {2: {"1": 9 * DAY}, 3: {"1": 16 * DAY}}                      # no kickoff in week 1: free agent
    pts = {1: {"1": 7.0}, 2: {"1": 20.5}, 3: {"1": 11.0}}
    d = _only(drops.build(_ctx(act, rosters=rosters, pts=pts, kickoff=kickoff, now={"1": 2})))
    assert (d["team"], d["id"], d["name"], d["pos"], d["pro_team"]) == (1, "1", "Alpha", "WR", "KC")
    assert d["weeks"] == [{"week": 1, "points": 7.0, "holder": None, "started": False},
                          {"week": 2, "points": 20.5, "holder": 2, "started": True},
                          {"week": 3, "points": 11.0, "holder": 2, "started": False}]
    assert (d["points_since"], d["weeks_since"]) == (38.5, 3)
    assert d["for_others"] == {"points": 31.5, "started_points": 20.5}    # week 1 was nobody's
    assert (d["now_team"], d["readded"], d["date"]) == (2, False, 0)


def test_a_week_on_the_droppers_own_box_score_roster_is_not_for_others():
    act = [_row(0, (1, "DROPPED", "1", 0))]
    rosters = {2: {1: _roster("1", started=["1"])}}
    d = _only(drops.build(_ctx(act, rosters=rosters, kickoff={2: {"1": 9 * DAY}}, pts={2: {"1": 5.0}})))
    assert d["weeks"][1]["holder"] == 1
    assert d["for_others"] == {"points": 0.0, "started_points": 0.0}


def test_a_team_that_picked_him_up_after_his_game_was_not_his_holder():
    act = [_row(0, (1, "DROPPED", "1", 0)), _row(10 * DAY, (2, "FA ADDED", "1", 0))]
    rosters = {2: {2: _roster("1")}}
    late = {2: {2: {"1"}}}                                                # ctx.late: joined after kickoff
    pts = {2: {"1": 12.0}}
    d = _only(drops.build(_ctx(act, rosters=rosters, kickoff={2: {"1": 9 * DAY}}, pts=pts, late=late)))
    assert d["weeks"][1] == {"week": 2, "points": 12.0, "holder": None, "started": False}
    assert d["for_others"]["points"] == 0.0


# ── the window ─────────────────────────────────────────────────────────────────
def test_window_closes_when_the_same_team_gets_him_back():
    act = [_row(0, (1, "DROPPED", "1", 0)),
           _row(7 * DAY, (1, "WAIVER ADDED", "1", 5))]  # back between weeks 1 and 2
    rosters = {1: {2: _roster("1")}, 2: {1: _roster("1")}, 3: {1: _roster("1")}}
    kickoff = {1: {"1": 2 * DAY}, 2: {"1": 9 * DAY}, 3: {"1": 16 * DAY}}
    pts = {1: {"1": 8.0}, 2: {"1": 30.0}, 3: {"1": 30.0}}
    d = _only(drops.build(_ctx(act, rosters=rosters, kickoff=kickoff, pts=pts)))
    assert [x["week"] for x in d["weeks"]] == [1] and d["points_since"] == 8.0
    assert d["readded"] is True


def test_a_trade_back_also_closes_the_window_but_another_teams_add_does_not():
    kickoff = {1: {"1": 2 * DAY}, 2: {"1": 9 * DAY}, 3: {"1": 16 * DAY}}
    pts = {1: {"1": 1.0}, 2: {"1": 2.0}, 3: {"1": 4.0}}
    traded_back = [_row(0, (1, "DROPPED", "1", 0)), _row(7 * DAY, (1, "TRADE_RECEIVED", "1", 0))]
    other_team = [_row(0, (1, "DROPPED", "1", 0)), _row(7 * DAY, (2, "FA ADDED", "1", 0))]
    assert _only(drops.build(_ctx(traded_back, kickoff=kickoff, pts=pts)))["weeks_since"] == 1
    assert _only(drops.build(_ctx(other_team, kickoff=kickoff, pts=pts)))["weeks_since"] == 3


def test_he_counts_for_the_week_whose_game_kicked_off_before_the_team_took_him_back():
    act = [_row(0, (1, "DROPPED", "1", 0)), _row(3 * DAY, (1, "FA ADDED", "1", 0))]
    early = _ctx(act, kickoff={1: {"1": 2 * DAY}}, pts={1: {"1": 6.0}})     # played before the re-add
    late = _ctx(act, kickoff={1: {"1": 4 * DAY}}, pts={1: {"1": 6.0}})      # played after it
    assert _only(drops.build(early))["points_since"] == 6.0
    assert _only(drops.build(late))["points_since"] == 0.0


def test_dropped_twice_is_two_entries_each_with_its_own_window():
    act = [_row(0, (1, "DROPPED", "1", 0)),
           _row(DAY // 2, (1, "FA ADDED", "1", 0)),    # took him back before any game
           _row(6 * DAY, (1, "DROPPED", "1", 0))]      # cut again before week 2
    pts = {1: {"1": 5.0}, 2: {"1": 9.0}, 3: {"1": 4.0}}
    out = drops.build(_ctx(act, pts=pts))
    first, second = sorted(out["drops"], key=lambda d: d["date"])
    assert (first["readded"], first["weeks_since"], first["points_since"]) == (True, 0, 0.0)
    assert (second["readded"], second["weeks_since"], second["points_since"]) == (False, 2, 13.0)
    assert out["teams"][0] == {"team": 1, "drops": 2, "regret_points": 13.0}


# ── which weeks count ──────────────────────────────────────────────────────────
def test_a_drop_after_his_game_does_not_claim_that_week():
    act = [_row(3 * DAY, (1, "DROPPED", "1", 0))]                           # Sunday night, week 1 in progress
    rosters = {1: {1: _roster("1", started=["1"])}}                        # still on its week-1 box score
    kickoff = {1: {"1": 2 * DAY}, 2: {"1": 9 * DAY}}                       # his week-1 game came first
    pts = {1: {"1": 25.0}, 2: {"1": 3.0}, 3: {"1": 1.0}}
    d = _only(drops.build(_ctx(act, rosters=rosters, kickoff=kickoff, pts=pts)))
    assert [x["week"] for x in d["weeks"]] == [2, 3] and d["points_since"] == 4.0


def test_a_drop_before_his_game_in_the_same_week_does_claim_it():
    act = [_row(3 * DAY, (1, "DROPPED", "1", 0))]
    kickoff = {1: {"1": 4 * DAY}}                                          # he played after the drop
    d = _only(drops.build(_ctx(act, kickoff=kickoff, pts={1: {"1": 25.0}, 2: {}, 3: {}})))
    assert [x["week"] for x in d["weeks"]] == [1, 2, 3] and d["points_since"] == 25.0


def test_free_agent_weeks_with_no_kickoff_use_the_weeks_first_kickoff():
    pts = {1: {"1": 4.0}, 2: {"1": 6.0}, 3: {"1": 9.0}}
    before_week_2 = _ctx([_row(6 * DAY, (1, "DROPPED", "1", 0))], pts=pts)
    in_week_2 = _ctx([_row(9 * DAY, (1, "DROPPED", "1", 0))], pts=pts)     # after week 2's first kickoff
    assert [x["week"] for x in _only(drops.build(before_week_2))["weeks"]] == [2, 3]
    out = _only(drops.build(in_week_2))
    assert [x["week"] for x in out["weeks"]] == [3] and out["points_since"] == 9.0


def test_a_free_agents_game_start_comes_from_a_teammate_on_a_fantasy_roster():
    # Dropped Sunday morning of week 2 (day 9.5), after Thursday's first kickoff (day 8). Player "1"
    # is on no roster, but "2" (same NFL team, KC) kicked off at day 10, so his game was still to come.
    act = [_row(int(9.5 * DAY), (1, "DROPPED", "1", 0))]
    kickoff = {2: {"2": 10 * DAY}}
    pts = {1: {"1": 3.0}, 2: {"1": 29.5}, 3: {"1": 2.0}}
    d = _only(drops.build(_ctx(act, kickoff=kickoff, pts=pts)))
    assert [x["week"] for x in d["weeks"]] == [2, 3] and d["points_since"] == 31.5
    # A teammate whose game had already kicked off (day 9) rules that week out: "3" is a BUF QB.
    act = [_row(int(9.5 * DAY), (1, "DROPPED", "3", 0))]
    d = _only(drops.build(_ctx(act, kickoff={2: {"4": 9 * DAY}}, pts={2: {"3": 40.0}, 3: {"3": 1.0}},
                               pos={"4": "WR"}, pro={"4": "BUF"})))
    assert [x["week"] for x in d["weeks"]] == [3] and d["points_since"] == 1.0


def test_a_player_with_no_nfl_team_never_borrows_a_kickoff():
    act = [_row(int(9.5 * DAY), (1, "DROPPED", "1", 0))]
    ctx = _ctx(act, kickoff={2: {"2": 10 * DAY}}, pts={2: {"1": 29.5}, 3: {"1": 2.0}}, pro={"1": "None", "2": "None"})
    d = _only(drops.build(ctx))
    assert [x["week"] for x in d["weeks"]] == [3] and d["pro_team"] == ""    # week-2 first kickoff stands in


# ── who is left out, and the summary ───────────────────────────────────────────
def test_kickers_head_coaches_and_defenders_are_left_out():
    act = [_row(0, (1, "DROPPED", "9", 0)), _row(0, (1, "DROPPED", "7", 0)), _row(0, (1, "DROPPED", "8", 0))]
    ctx = _ctx(act, pos={"7": "HC", "8": "LB"})
    assert drops.build(ctx) is None
    act.append(_row(0, (2, "DROPPED", "3", 0)))
    assert [d["id"] for d in drops.build(_ctx(act, pos={"7": "HC", "8": "LB"}))["drops"]] == ["3"]


def test_no_drops_means_no_report():
    assert drops.build(_ctx([])) is None
    assert drops.build(_ctx([_row(0, (1, "FA ADDED", "1", 0))])) is None


def test_a_drop_after_the_last_completed_week_stays_in_the_data_with_no_weeks():
    act = [_row(25 * DAY, (1, "DROPPED", "1", 0))]
    d = _only(drops.build(_ctx(act, pts={1: {"1": 9.0}, 2: {"1": 9.0}, 3: {"1": 9.0}})))
    assert (d["weeks_since"], d["points_since"], d["weeks"]) == (0, 0.0, [])
    assert (d["for_others"], d["now_team"]) == ({"points": 0.0, "started_points": 0.0}, None)


def test_drops_are_sorted_by_points_and_the_team_summary_adds_them_up():
    act = [_row(0, (1, "DROPPED", "1", 0)), _row(0, (1, "DROPPED", "2", 0)), _row(0, (2, "DROPPED", "3", 0))]
    pts = {w: {"1": 5.0, "2": 10.0, "3": 1.0} for w in (1, 2, 3)}
    out = drops.build(_ctx(act, pts=pts))
    assert out["through"] == 3
    assert [(d["id"], d["points_since"]) for d in out["drops"]] == [("2", 30.0), ("1", 15.0), ("3", 3.0)]
    assert out["teams"] == [{"team": 1, "drops": 2, "regret_points": 45.0},
                            {"team": 2, "drops": 1, "regret_points": 3.0},
                            {"team": 3, "drops": 0, "regret_points": 0.0}]


def test_missing_current_rosters_just_leave_now_team_empty():
    act = [_row(0, (1, "DROPPED", "1", 0))]
    ctx = _ctx(act, pts={1: {"1": 1.0}})
    del ctx.lg
    assert _only(drops.build(ctx))["now_team"] is None
