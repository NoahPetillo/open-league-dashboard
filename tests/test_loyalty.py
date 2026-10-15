"""Player loyalty: day-one players, who kept their picks, and the revolving doors."""

from __future__ import annotations

from types import SimpleNamespace

from league import loyalty

POS = {"a": "WR", "b": "RB", "c": "WR", "d": "WR", "e": "TE", "f": "WR", "g": "RB", "h": "WR"}


def _row(date, *moves):
    return {"date": date, "moves": list(moves)}


def _pick(n, team, pid):
    return {"pick": n, "round": 1, "round_pick": n, "team": team, "id": pid, "name": pid.upper()}


def _ctx(draft, activity, now, *, pts=None, weeks=(1, 2), pos=None):
    """``now`` maps team id → the player ids on its roster today."""
    lg = SimpleNamespace(teams=[SimpleNamespace(team_id=t, roster=[SimpleNamespace(playerId=p) for p in ids])
                                for t, ids in now.items()])
    pos = pos or POS
    return SimpleNamespace(draft=draft, activity=activity, lg=lg, weeks=list(weeks), pts=pts or {},
                           pos=pos, names={p: f"Player {p.upper()}" for p in pos},
                           teams=[{"id": t} for t in now])


def _team(out, tid):
    return next(t for t in out["teams"] if t["team"] == tid)


# Team 1 drafts a, b, c; team 2 drafts d, e, g. Then:
#   team 1 drops b and takes him back, drops c (team 2 claims him), adds f, trades for g;
#   team 2 adds h.
DRAFT = [_pick(1, 1, "a"), _pick(2, 2, "d"), _pick(3, 2, "e"), _pick(4, 1, "b"), _pick(5, 1, "c"), _pick(6, 2, "g")]
ACTIVITY = [
    _row(10, (1, "DROPPED", "b", 0)),
    _row(20, (1, "FA ADDED", "b", 0)),
    _row(30, (1, "DROPPED", "c", 0)),
    _row(31, (2, "WAIVER ADDED", "c", 4)),
    _row(40, (1, "FA ADDED", "f", 0)),
    _row(50, (2, "TRADE_SENT", "g", 0), (1, "TRADE_RECEIVED", "g", 0)),
    _row(60, (2, "FA ADDED", "h", 0)),
]
NOW = {1: ["a", "b", "f", "g"], 2: ["c", "d", "e", "h"]}
PTS = {1: {"a": 10.0, "b": 8.0, "d": 3.0, "e": 5.0}, 2: {"a": 12.5, "b": 1.0, "d": 4.0, "e": 0.0}, 3: {"a": 99.0}}


def test_a_player_dropped_and_re_added_is_kept_but_not_day_one():
    out = loyalty.build(_ctx(DRAFT, ACTIVITY, NOW, pts=PTS))
    one = _team(out, 1)
    assert (one["drafted"], one["kept"]) == (3, 2)                  # a and b are home; c left
    assert one["day_ones"] == [{"id": "a", "name": "Player A", "pos": "WR", "points": 22.5}]
    two = _team(out, 2)
    assert (two["drafted"], two["kept"]) == (3, 2)                  # g was traded away
    assert [p["id"] for p in two["day_ones"]] == ["d", "e"]         # best season first (7.0 and 5.0)
    assert [p["points"] for p in two["day_ones"]] == [7.0, 5.0]


def test_a_pick_who_moved_anywhere_is_not_day_one_even_for_a_team_that_still_has_him():
    # Team 2 drafted "e"; team 1 adds and drops him once, and he ends up back with team 2.
    act = [_row(1, (1, "FA ADDED", "e", 0)), _row(2, (1, "DROPPED", "e", 0)), _row(3, (2, "FA ADDED", "e", 0))]
    out = loyalty.build(_ctx(DRAFT, act, {1: ["a"], 2: ["d", "e"]}))
    assert [p["id"] for p in _team(out, 2)["day_ones"]] == ["d"]
    assert _team(out, 2)["kept"] == 2


def test_a_pick_traded_away_and_back_is_kept_and_counted_once():
    act = [_row(1, (2, "TRADE_SENT", "d", 0), (1, "TRADE_RECEIVED", "d", 0)),
           _row(2, (1, "TRADE_SENT", "d", 0), (2, "TRADE_RECEIVED", "d", 0))]
    out = loyalty.build(_ctx(DRAFT, act, {1: ["a"], 2: ["d", "e"]}))
    two = _team(out, 2)
    assert (two["kept"], two["distinct"]) == (2, 3)                 # d, e, g: d is not counted twice
    assert [p["id"] for p in two["day_ones"]] == ["e"]


def test_distinct_players_include_the_draft_adds_and_trades_in_by_position():
    out = loyalty.build(_ctx(DRAFT, ACTIVITY, NOW))
    one, two = _team(out, 1), _team(out, 2)
    assert one["distinct"] == 5 and one["by_pos"] == {"WR": 3, "RB": 2}   # a b c + f + g (b's re-add is not new)
    assert two["distinct"] == 5 and two["by_pos"] == {"WR": 3, "RB": 1, "TE": 1}  # d e g + c + h
    assert list(two["by_pos"]) == ["WR", "RB", "TE"]                # biggest group first


def test_a_player_who_only_left_is_not_counted_for_the_team_that_lost_him():
    out = loyalty.build(_ctx(DRAFT, [_row(1, (2, "DROPPED", "d", 0))], {1: ["a", "b", "c"], 2: ["e", "g"]}))
    assert _team(out, 2)["distinct"] == 3 and _team(out, 2)["kept"] == 2


def test_revolving_doors_list_players_in_arrival_order_and_rank_by_count():
    out = loyalty.build(_ctx(DRAFT, ACTIVITY, NOW))
    doors = out["revolving_doors"]
    assert [(d["team"], d["pos"], d["count"]) for d in doors[:3]] == [(2, "WR", 3), (1, "WR", 3), (1, "RB", 2)]
    # Team 2's WRs: drafted d first, then the waiver claim c (day 31), then h (day 60).
    assert doors[0]["players"] == ["Player D", "Player C", "Player H"]
    assert doors[1]["players"] == ["Player A", "Player C", "Player F"]   # draft picks a, c, then f
    assert [d["drafted"] for d in doors[:2]] == [1, 2]                  # tie goes to the team with more churn
    assert doors[2]["players"] == ["Player B", "Player G"]


def test_a_door_can_be_any_position_and_only_the_top_six_are_kept():
    pos = {f"p{i}": "WR" for i in range(7)} | {"k1": "K", "k2": "K", "k3": "K"}
    draft = [_pick(i + 1, 1, f"p{i}") for i in range(7)]
    act = [_row(1, (2, "FA ADDED", "k1", 0)), _row(2, (2, "FA ADDED", "k2", 0)), _row(3, (2, "FA ADDED", "k3", 0))]
    out = loyalty.build(_ctx(draft, act, {1: [f"p{i}" for i in range(7)], 2: ["k1"]}, pos=pos))
    assert [(d["team"], d["pos"], d["count"]) for d in out["revolving_doors"]] == [(1, "WR", 7), (2, "K", 3)]
    many = {f"x{i}": f"POS{i}" for i in range(8)}
    act = [_row(i, (1, "FA ADDED", f"x{i}", 0)) for i in range(8)]
    out = loyalty.build(_ctx(DRAFT, act, NOW, pos=POS | many))
    assert len(out["revolving_doors"]) == 6


def test_ride_or_die_is_the_top_ten_day_ones_league_wide():
    pos = {f"p{i}": "RB" for i in range(14)}
    draft = [_pick(i + 1, 1 + i % 2, f"p{i}") for i in range(14)]
    pts = {1: {f"p{i}": float(i) for i in range(14)}, 2: {f"p{i}": 1.0 for i in range(14)}}
    now = {1: [f"p{i}" for i in range(0, 14, 2)], 2: [f"p{i}" for i in range(1, 14, 2)]}
    out = loyalty.build(_ctx(draft, [], now, pts=pts, pos=pos))
    rows = out["ride_or_die"]
    assert len(rows) == 10
    assert [r["id"] for r in rows][:3] == ["p13", "p12", "p11"]       # 14, 13, 12 points (season = sum of two weeks)
    assert rows[0] == {"team": 2, "id": "p13", "name": "Player P13", "pos": "RB", "points": 14.0}
    assert [r["points"] for r in rows] == sorted((r["points"] for r in rows), reverse=True)


def test_season_points_only_cover_completed_weeks():
    out = loyalty.build(_ctx(DRAFT, [], {1: ["a"], 2: ["d"]}, pts=PTS, weeks=(1,)))
    assert _team(out, 1)["day_ones"][0]["points"] == 10.0             # week 2 and the unplayed week 3 are out


def test_no_draft_or_no_rosters_means_no_report():
    assert loyalty.build(_ctx([], ACTIVITY, NOW)) is None
    assert loyalty.build(_ctx(DRAFT, ACTIVITY, {1: [], 2: []})) is None
    ctx = _ctx(DRAFT, ACTIVITY, NOW)
    del ctx.lg
    assert loyalty.build(ctx) is None
