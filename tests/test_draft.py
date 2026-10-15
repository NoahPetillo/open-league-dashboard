"""Draft report card: points vs. draft slot, statuses, let-go weeks, the grading curve, highlights."""

from __future__ import annotations

from types import SimpleNamespace

from league import draft

# Two completed weeks. Week 1's games end at t=200, week 2's at t=400.
KICKS = {1: (100, 200), 2: (300, 400)}

#          pick  round rd_pick team  id     pos   week-1 + week-2 points
PLAYERS = [(1, 1, 1, 1, "101", "QB", 10, 20),   # a: 30
           (2, 1, 2, 2, "102", "WR", 15, 25),   # b: 40 (ties with c)
           (3, 1, 3, 3, "103", "RB", 40, 0),    # c: 40
           (4, 2, 1, 3, "104", "K", 50, 49),    # d: 99, a kicker: listed, not graded
           (5, 2, 2, 2, "105", "TE", 5, 0),     # e: 5
           (6, 2, 3, 1, "106", "WR", 0, 0),     # f: 0 (ties with i)
           (7, 3, 1, 1, "107", "HC", 7, 0),     # g: 7, a head coach: not graded
           (8, 3, 2, 2, "108", "RB", 30, 30),   # h: 60
           (9, 3, 3, 3, "109", "WR", 0, 0)]     # i: 0


def _move(date, team, kind, pid):
    return {"date": date, "moves": [(team, kind, pid, 0)]}


def _ctx(activity=None, rosters=None, players=PLAYERS, kicks=KICKS):
    """Three teams, three rounds. Rosters default to: a, f, e, i kept; c on team 1; b on team 3."""
    if rosters is None:
        rosters = {1: [101, 106, 103], 2: [105], 3: [109, 102]}
    teams = [SimpleNamespace(team_id=t, roster=[SimpleNamespace(playerId=p) for p in ids])
             for t, ids in rosters.items()]
    return SimpleNamespace(
        through=2, weeks=[1, 2], kicks=kicks, activity=activity or [], lg=SimpleNamespace(teams=teams),
        draft=[{"pick": n, "round": r, "round_pick": rp, "team": t, "id": pid, "name": f"P{pid}"}
               for n, r, rp, t, pid, _pos, _w1, _w2 in players],
        pos={pid: pos for _n, _r, _rp, _t, pid, pos, _w1, _w2 in players},
        pro={pid: "KC" for _n, _r, _rp, _t, pid, _pos, _w1, _w2 in players},
        names={}, pts={1: {p[4]: p[6] for p in players}, 2: {p[4]: p[7] for p in players}})


ACTIVITY = [
    _move(120, 2, "DROPPED", "108"),        # h: dropped in week 1 ...
    _move(130, 2, "FA ADDED", "108"),       # ... re-added ...
    _move(320, 2, "DROPPED", "108"),        # ... dropped again in week 2; free agent now
    _move(250, 2, "DROPPED", "102"),        # b: dropped between weeks 1 and 2 (lands in week 2); team 3 has him
    _move(260, 3, "FA ADDED", "102"),
    _move(150, 3, "TRADE_SENT", "103"),     # c: traded by team 3 to team 1 in week 1
    _move(150, 1, "TRADE_RECEIVED", "103"),
    _move(450, 3, "DROPPED", "104"),        # d: dropped after week 2's last kickoff
    _move(50, 1, "DROPPED", "106"),         # f: preseason drop ...
    _move(260, 1, "FA ADDED", "106"),       # ... and back
    _move(100, 1, "DROPPED", "109"),        # team 1 never had i: someone else's drop doesn't count
]


def _build(**kw):
    out = draft.build(_ctx(ACTIVITY, **kw))
    assert out is not None
    return out


def _pick(out, n):
    return next(p for p in out["picks"] if p["pick"] == n)


def _team(out, tid):
    return next(t for t in out["teams"] if t["team"] == tid)


# ── grading ────────────────────────────────────────────────────────────────────
def test_points_sum_every_completed_week():
    out = _build()
    assert [_pick(out, n)["points"] for n in range(1, 10)] == [30, 40, 40, 99, 5, 0, 7, 60, 0]
    assert (out["through"], out["rounds"], out["teams_n"]) == (2, 3, 3)


def test_rank_ties_share_the_best_rank_and_value_is_order_minus_rank():
    out = _build()
    # Skill picks in draft order: a b c e f h i → order 1..7. By points: h 60, b/c 40, a 30, e 5, f/i 0.
    got = {n: (p["order"], p["points_rank"], p["value"]) for n in (1, 2, 3, 5, 6, 8, 9)
           for p in [_pick(out, n)]}
    assert got == {1: (1, 4, -3), 2: (2, 2, 0), 3: (3, 2, 1), 5: (4, 5, -1),
                   6: (5, 6, -1), 8: (6, 1, 5), 9: (7, 6, 1)}


def test_specialists_are_listed_but_not_graded():
    out = _build()
    for n in (4, 7):
        p = _pick(out, n)
        assert p["skill"] is False
        assert (p["order"], p["points_rank"], p["value"]) == (None, None, None)
    assert _pick(out, 4)["points"] == 99  # kicker's points don't push anyone down the ranking
    assert _pick(out, 8)["points_rank"] == 1 and _pick(out, 1)["skill"] is True
    assert (_pick(out, 4)["pos"], _pick(out, 4)["pro_team"], _pick(out, 4)["name"]) == ("K", "KC", "P104")


def test_missing_points_count_as_zero_and_unknown_positions_are_ungraded():
    ctx = _ctx(ACTIVITY)
    del ctx.pts[2]["101"]
    del ctx.pos["102"]
    out = draft.build(ctx)
    assert _pick(out, 1)["points"] == 10
    assert _pick(out, 2)["pos"] == "?" and _pick(out, 2)["value"] is None


# ── what happened to each pick ─────────────────────────────────────────────────
def test_statuses_and_now_team():
    out = _build()
    got = {n: (_pick(out, n)["status"], _pick(out, n)["now_team"]) for n in range(1, 10)}
    assert got == {
        1: ("kept", 1),
        2: ("dropped", 3),     # dropped by team 2, picked up by team 3
        3: ("traded", 1),      # traded by team 3 to team 1
        4: ("dropped", None),  # dropped and still a free agent
        5: ("kept", 2),
        6: ("kept", 1),        # dropped in the preseason, re-added by the same team
        7: ("gone", None),     # off the roster, and ESPN logged no move
        8: ("dropped", None),  # dropped twice: the last one took him off
        9: ("kept", 3),
    }


def test_let_go_week_is_the_first_completed_week_ending_after_the_move():
    out = _build()
    got = {n: _pick(out, n)["let_go_week"] for n in range(1, 10)}
    assert got == {1: None, 2: 2, 3: 1, 4: None, 5: None, 6: 1, 7: None, 8: 1, 9: None}


def test_let_go_week_edges():
    def week(date):
        ctx = _ctx([_move(date, 2, "DROPPED", "102")])
        return _pick(draft.build(ctx), 2)["let_go_week"]
    assert (week(0), week(199), week(200), week(399), week(400), week(10_000)) == (1, 1, 2, 2, None, None)


def test_a_week_with_no_kickoff_data_is_skipped():
    ctx = _ctx([_move(250, 2, "DROPPED", "102")], kicks={2: (300, 400)})
    assert _pick(draft.build(ctx), 2)["let_go_week"] == 2
    ctx = _ctx([_move(250, 2, "DROPPED", "102")], kicks={})
    assert _pick(draft.build(ctx), 2)["let_go_week"] is None


def test_moves_without_a_team_are_ignored():
    ctx = _ctx([{"date": 120, "moves": [(None, "DROPPED", "102", 0)]}])
    assert _pick(draft.build(ctx), 2)["status"] == "gone"


def test_without_roster_data_nothing_is_called_kept():
    out = draft.build(_ctx(ACTIVITY, rosters={}))
    assert {p["status"] for p in out["picks"]} == {None}
    assert {p["now_team"] for p in out["picks"]} == {None}
    assert _pick(out, 2)["let_go_week"] == 2  # the activity feed still says when
    assert all(t["kept"] is None and t["kept_points"] is None for t in out["teams"])
    assert out["highlights"]["kept_most"] is None and out["highlights"]["earliest_cut"] is None
    assert _team(out, 2)["grade"] is not None  # grading doesn't need rosters


# ── teams ──────────────────────────────────────────────────────────────────────
def test_team_rows():
    out = _build()
    assert [t["team"] for t in out["teams"]] == [2, 3, 1]  # by rank
    t1, t2, t3 = _team(out, 1), _team(out, 2), _team(out, 3)
    assert (t1["graded"], t1["value_avg"], t1["points"]) == (2, -2.0, 37)
    assert (t2["graded"], t2["value_avg"], t2["points"]) == (3, 1.33, 105)
    assert (t3["graded"], t3["value_avg"], t3["points"]) == (2, 1.0, 139)
    assert [(t["kept"], t["kept_points"]) for t in (t1, t2, t3)] == [(2, 30), (1, 5), (1, 0)]
    # Best and worst by value; a tie on value goes to the pick with more (or fewer) points.
    assert [(t["best_pick"], t["worst_pick"]) for t in (t1, t2, t3)] == [(6, 1), (8, 5), (3, 9)]


def test_curve_for_three_teams():
    out = _build()
    assert [(t["team"], t["rank"], t["grade"]) for t in out["teams"]] == [(2, 1, "A+"), (3, 2, "C+"), (1, 3, "F")]


def test_tied_averages_share_the_better_grade():
    # Orders 1..6 go 1,2,3,3,2,1. Points ranks 3,1,2,4,5,6 give values -2,+1,+1,0,0,0, so teams 2 and 3
    # both average +0.5 and team 1 averages -1.0.
    plan = [(1, 1, 1, 1, "201", 40), (2, 1, 2, 2, "202", 60), (3, 1, 3, 3, "203", 50),
            (4, 2, 1, 3, "204", 30), (5, 2, 2, 2, "205", 20), (6, 2, 3, 1, "206", 10)]
    players = [(n, r, rp, t, pid, "QB", pts, 0) for n, r, rp, t, pid, pts in plan]
    out = draft.build(_ctx(players=players, rosters={1: [], 2: [], 3: []}))
    assert [_pick(out, n)["value"] for n in range(1, 7)] == [-2, 1, 1, 0, 0, 0]
    got = {t["team"]: (t["rank"], t["grade"], t["value_avg"]) for t in out["teams"]}
    assert got == {2: (1, "A+", 0.5), 3: (1, "A+", 0.5), 1: (3, "F", -1.0)}


def _row(team, *values, kept=0):
    picks = [{"team": team, "skill": True, "value": v, "points": 0.0, "pick": i, "status": "kept"}
             for i, v in enumerate(values)]
    picks += [{"team": team, "skill": False, "value": None, "points": 0.0, "pick": 99, "status": "gone"}] * kept
    return picks


def test_equal_averages_tie_even_when_pick_counts_differ():
    picks = _row(1, 2, 2) + _row(2, 1, 2, 3) + _row(3, -5)
    got = {t["team"]: (t["rank"], t["grade"]) for t in draft._team_rows(picks, True)}
    assert got == {1: (1, "A+"), 2: (1, "A+"), 3: (3, "F")}


def test_twelve_teams_get_the_whole_scale_in_order():
    picks = [p for t in range(1, 13) for p in _row(t, 100 - t)]
    rows = draft._team_rows(picks, True)
    assert [r["grade"] for r in rows] == draft.SCALE
    assert [r["team"] for r in rows] == list(range(1, 13)) and [r["rank"] for r in rows] == list(range(1, 13))


def test_the_scale_spreads_for_other_team_counts():
    def grades(n):
        picks = [p for t in range(1, n + 1) for p in _row(t, 100 - t)]
        return [r["grade"] for r in draft._team_rows(picks, True)]
    assert grades(1) == ["A+"] and grades(2) == ["A+", "F"]
    for n in (4, 8, 16, 30):
        g = [draft.SCALE.index(x) for x in grades(n)]
        assert g[0] == 0 and g[-1] == 11 and g == sorted(g)
    assert grades(24).count("A+") == 2 and grades(24).count("F") == 2


def test_a_team_with_nothing_to_grade_is_left_off_the_curve():
    picks = _row(1, 5) + _row(2, kept=2)
    rows = {r["team"]: r for r in draft._team_rows(picks, True)}
    assert rows[2]["grade"] is None and rows[2]["rank"] is None and rows[2]["value_avg"] is None
    assert rows[2]["best_pick"] is None and rows[1]["grade"] == "A+"
    assert [r["team"] for r in draft._team_rows(picks, True)] == [1, 2]  # ungraded last


# ── highlights ─────────────────────────────────────────────────────────────────
def test_highlights():
    h = _build()["highlights"]
    assert h == {
        "steal": 8,                 # h: value +5
        "bust": 1,                  # a: value -3
        "worst_first_rounder": 1,   # a: 30 points, the fewest of round 1
        "best_first_rounder": 2,    # b and c tie on 40: the earlier pick wins
        "earliest_cut": 2,          # b: lowest pick among those dropped by the team that drafted him
        "kept_most": 1,             # team 1 kept two
    }


def test_highlight_ties_and_absences():
    # Nobody dropped anyone: no earliest cut. Teams tie on kept: more kept points wins.
    out = draft.build(_ctx([], rosters={1: [101, 106], 2: [102, 105], 3: [109, 103]}))
    h = out["highlights"]
    assert h["earliest_cut"] is None
    assert [_team(out, t)["kept"] for t in (1, 2, 3)] == [2, 2, 2]
    assert h["kept_most"] == 2  # kept_points: team 1 = 30, team 2 = 45, team 3 = 40


def test_a_traded_pick_is_not_a_cut():
    ctx = _ctx([_move(150, 3, "TRADE_SENT", "103"), _move(150, 1, "TRADE_RECEIVED", "103")])
    assert draft.build(ctx)["highlights"]["earliest_cut"] is None


def test_no_draft_means_no_report():
    ctx = _ctx()
    ctx.draft = []
    assert draft.build(ctx) is None


def test_output_is_plain_json():
    import json
    out = _build()
    assert json.loads(json.dumps(out)) == out
    assert set(out["picks"][0]) == {"pick", "round", "round_pick", "team", "id", "name", "pos", "pro_team",
                                    "points", "skill", "order", "points_rank", "value", "status",
                                    "now_team", "let_go_week"}
    assert set(out["teams"][0]) == {"team", "grade", "rank", "value_avg", "graded", "points", "kept",
                                    "kept_points", "best_pick", "worst_pick"}
