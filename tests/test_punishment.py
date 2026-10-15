"""Last-place race simulation."""

from __future__ import annotations

from league.punishment import byes_for, playoff_field, simulate


def _league():
    # 4 teams, team 4 is awful, two weeks left: 1v4 & 2v3, then 1v3 & 2v4.
    teams = [{"id": i, "wins": w, "losses": 2 - w, "ties": 0, "points_for": sum(sc), "scores": sc}
             for i, w, sc in [(1, 2, [150, 160]), (2, 1, [130, 135]), (3, 1, [128, 132]),
                              (4, 0, [80, 85])]]
    schedule = {3: [(1, 4), (2, 3)], 4: [(1, 3), (2, 4)]}
    return teams, schedule


def test_worst_team_is_most_likely_last_and_odds_sum_to_one():
    teams, schedule = _league()
    out = simulate(teams, schedule, [3, 4], sims=4000)
    p = {t["id"]: t["p_last"] for t in out["teams"]}
    assert max(p, key=p.get) == 4
    assert abs(sum(p.values()) - 1) < 1e-6
    assert sum(out["last_place_wins"].values()) > 0.999


def test_winning_next_week_lowers_last_place_odds():
    teams, schedule = _league()
    out = simulate(teams, schedule, [3, 4], sims=4000)
    t4 = next(t for t in out["teams"] if t["id"] == 4)
    assert t4["next_if_win"] < t4["next_if_loss"]
    assert {(g["a"], g["b"]) for g in out["next_week_games"]} == {(1, 4), (2, 3)}


def test_magic_number_and_wins_needed():
    teams, schedule = _league()
    out = simulate(teams, schedule, [3, 4], sims=4000)
    magic = out["magic_number"]
    assert magic is not None
    for t, state in zip(out["teams"], teams, strict=True):
        assert t["need"] == max(0, magic - state["wins"])
        assert 0 <= t["p_reach_magic"] <= 1


def test_same_seed_same_answer():
    teams, schedule = _league()
    assert simulate(teams, schedule, [3, 4], sims=500) == simulate(teams, schedule, [3, 4], sims=500)


# ── playoff odds ───────────────────────────────────────────────────────────────
def _six_team_league():
    """Two divisions of three; 4 playoff spots (no byes). Week 3 is the last one left."""
    divisions = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1}
    state = [(1, 2, [150, 160]), (2, 1, [130, 135]), (3, 0, [90, 95]),
             (4, 2, [140, 150]), (5, 1, [120, 125]), (6, 0, [85, 90])]
    teams = [{"id": i, "wins": w, "losses": 2 - w, "ties": 0, "points_for": sum(sc), "scores": sc}
             for i, w, sc in state]
    return teams, {3: [(1, 2), (3, 4), (5, 6)]}, divisions


def test_playoff_field_gives_division_winners_the_top_seeds():
    # Team 3 wins a weak division with 4 wins; teams 4 and 5 have better records but share
    # a division. Spots: 3 (two winners + one wild card).
    wins = {1: 9, 2: 8, 3: 4, 4: 7, 5: 6, 6: 5}
    pf = {t: 1000.0 + t for t in wins}
    groups = [[1, 2, 3], [4, 5, 6]]
    seeds, champs = playoff_field(list(wins), groups, wins, pf, dict.fromkeys(wins, 0), 3)
    assert champs == [1, 4]
    assert seeds == [1, 4, 2]  # the third spot is the best record left


def test_division_winner_with_a_bad_record_still_gets_in():
    wins = {1: 9, 2: 8, 3: 7, 4: 2, 5: 1, 6: 0}
    pf = {t: 1000.0 + t for t in wins}
    seeds, champs = playoff_field(list(wins), [[1, 2, 3], [4, 5, 6]], wins, pf,
                                  dict.fromkeys(wins, 0), 3)
    assert champs == [1, 4]
    assert seeds == [1, 4, 2]  # team 4 (2 wins) is in and seeded above team 2 (8 wins)


def test_playoff_field_breaks_division_ties_on_division_wins_then_points():
    wins = {1: 7, 2: 7, 3: 7, 4: 7}
    pf = {1: 900.0, 2: 950.0, 3: 880.0, 4: 870.0}
    groups = [[1, 2], [3, 4]]
    seeds, champs = playoff_field([1, 2, 3, 4], groups, wins, pf, {1: 3, 2: 2, 3: 1, 4: 1}, 2)
    # Team 1 beats team 2 on division wins despite fewer points; 3 beats 4 on points.
    assert set(champs) == {1, 3}
    assert seeds == [1, 3]  # seeded by wins, then division wins (3 beats 1)


def test_wild_card_ties_go_to_division_record_before_points():
    wins = {1: 9, 2: 9, 3: 7, 4: 7}
    pf = {1: 1000.0, 2: 1000.0, 3: 1200.0, 4: 900.0}
    groups = [[1, 3], [2, 4]]
    # Division winners 1 and 2 are in; 3 and 4 tie on 7 wins for the last spot.
    seeds, _ = playoff_field([1, 2, 3, 4], groups, wins, pf, {1: 2, 2: 2, 3: 0, 4: 2}, 3)
    assert seeds[2] == 4  # 4's division wins beat 3's 300 extra points


def test_playoff_field_without_divisions_is_just_the_best_records():
    wins = {1: 3, 2: 5, 3: 5, 4: 1}
    pf = {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0}
    seeds, champs = playoff_field([1, 2, 3, 4], [], wins, pf, dict.fromkeys(wins, 0), 2)
    assert seeds == [3, 2] and champs == []


def test_byes_fill_the_bracket_to_a_power_of_two():
    assert [byes_for(n) for n in (0, 1, 2, 4, 6, 7, 8, 12)] == [0, 0, 0, 0, 2, 1, 0, 4]


def test_playoff_odds_add_up():
    teams, schedule, divisions = _six_team_league()
    out = simulate(teams, schedule, [3], sims=4000, playoff_teams=4, divisions=divisions)
    t = out["teams"]
    assert abs(sum(x["p_playoffs"] for x in t) - 4) < 2e-3   # exactly four teams get in
    assert abs(sum(x["p_division"] for x in t) - 2) < 2e-3   # one winner per division
    assert all(x["p_bye"] is None for x in t) and out["byes"] == 0 and out["playoff_spots"] == 4
    assert all(x["p_playoffs"] >= x["p_division"] for x in t)  # a division winner is always in
    p = {x["id"]: x for x in t}
    assert p[1]["p_division"] > 0.5 > p[2]["p_division"] and p[6]["p_playoffs"] < p[4]["p_playoffs"]


def test_bye_odds_go_to_top_seeds():
    # 4 divisions of 2, 6 spots → seeds 1 and 2 skip round one.
    teams = [{"id": i, "wins": 0, "losses": 0, "ties": 0, "points_for": 0, "scores": []}
             for i in range(1, 9)]
    schedule = {1: [(1, 2), (3, 4), (5, 6), (7, 8)], 2: [(1, 3), (2, 4), (5, 7), (6, 8)]}
    divisions = {1: 0, 2: 0, 3: 1, 4: 1, 5: 2, 6: 2, 7: 3, 8: 3}
    out = simulate(teams, schedule, [1, 2], sims=3000, playoff_teams=6, divisions=divisions)
    assert out["byes"] == 2
    t = out["teams"]
    assert abs(sum(x["p_bye"] for x in t) - 2) < 2e-3
    assert abs(sum(x["p_playoffs"] for x in t) - 6) < 2e-3
    assert all(x["p_bye"] <= x["p_division"] + 1e-9 for x in t)  # byes go to division winners here


def test_playoff_odds_do_not_change_the_last_place_race():
    teams, schedule = _league()
    plain = simulate(teams, schedule, [3, 4], sims=1000)
    with_odds = simulate(teams, schedule, [3, 4], sims=1000, playoff_teams=2,
                         divisions={1: 0, 2: 0, 3: 1, 4: 1})
    assert "p_playoffs" not in plain["teams"][0] and "playoff_spots" not in plain
    assert with_odds["next_week_games"] == plain["next_week_games"]
    for a, b in zip(plain["teams"], with_odds["teams"], strict=True):
        assert {k: v for k, v in b.items() if k in a} == a


def test_division_wins_so_far_decide_a_finished_season():
    # Season over: teams 1 and 2 finish 8-6 in one division; 1 has more division wins.
    teams = [{"id": i, "wins": w, "losses": 14 - w, "ties": 0, "points_for": pf,
              "scores": [pf / 14] * 14, "div_wins": dw}
             for i, w, pf, dw in [(1, 8, 1500.0, 4), (2, 8, 1700.0, 3), (3, 6, 1400.0, 2),
                                  (4, 3, 1200.0, 1)]]
    out = simulate(teams, {}, [], playoff_teams=2, divisions={1: 0, 2: 0, 3: 1, 4: 1})
    p = {t["id"]: t for t in out["teams"]}
    assert out["sims"] == 1 and out["next_week_games"] == []
    assert p[1]["p_division"] == 1 and p[2]["p_division"] == 0 and p[3]["p_division"] == 1
    assert p[1]["p_playoffs"] == 1 and p[3]["p_playoffs"] == 1 and p[2]["p_playoffs"] == 0
    assert p[4]["p_last"] == 1 and p[1]["p_last"] == 0


def test_last_place_ties_go_to_division_record_before_points():
    # Season over: teams 3 and 4 both finish 3-11; 3 scored more but won fewer division games.
    teams = [{"id": i, "wins": w, "losses": 14 - w, "ties": 0, "points_for": pf,
              "scores": [pf / 14] * 14, "div_wins": dw}
             for i, w, pf, dw in [(1, 10, 1500.0, 4), (2, 8, 1400.0, 3), (3, 3, 1300.0, 0),
                                  (4, 3, 1100.0, 2)]]
    out = simulate(teams, {}, [], playoff_teams=2, divisions={1: 0, 2: 1, 3: 0, 4: 1})
    p = {t["id"]: t for t in out["teams"]}
    assert p[3]["p_last"] == 1 and p[4]["p_last"] == 0


def test_division_games_give_division_wins():
    # Division 0 = {1, 2, 5}; division 1 = {3, 4, 6}. Team 1 (weak, 5 wins, lots of points)
    # loses to team 4, a non-division game. Team 2 (strong, 4 wins) beats team 5, a division
    # game. Both finish with 5 wins; team 2's division win beats team 1's extra points.
    def team(i, wins, pf, level):
        return {"id": i, "wins": wins, "losses": 0, "ties": 0, "points_for": pf, "scores": [level] * 10}
    teams = [team(1, 5, 5000.0, 0), team(2, 4, 100.0, 1000), team(3, 0, 0.0, 500),
             team(4, 0, 0.0, 1000), team(5, 0, 0.0, 0), team(6, 0, 0.0, 500)]
    divisions = {1: 0, 2: 0, 5: 0, 3: 1, 4: 1, 6: 1}
    out = simulate(teams, {1: [(1, 4), (2, 5), (3, 6)]}, [1], sims=200, playoff_teams=2,
                   divisions=divisions)
    p = {t["id"]: t for t in out["teams"]}
    assert p[2]["p_division"] == 1 and p[1]["p_division"] == 0 and p[5]["p_division"] == 0


def test_races_give_each_race_its_odds_magic_number_cutoff_and_swing_games():
    teams, schedule = _league()
    out = simulate(teams, schedule, [3, 4], sims=4000, playoff_teams=3)  # 3 in: seed 1 gets a bye
    races = out["races"]
    assert set(races) == {"last", "playoffs", "bye"}
    # last is the same race as the top-level fields
    assert [t["p"] for t in races["last"]["teams"]] == [t["p_last"] for t in out["teams"]]
    assert races["last"]["magic_number"] == out["magic_number"]
    po = {t["id"]: t for t in races["playoffs"]["teams"]}
    assert [po[t["id"]]["p"] for t in out["teams"]] == [t["p_playoffs"] for t in out["teams"]]
    assert abs(sum(t["p"] for t in po.values()) - 3) < 2e-3         # three spots, every sim
    assert abs(sum(t["p"] for t in races["bye"]["teams"]) - 1) < 2e-3  # one bye
    for key in ("playoffs", "bye"):
        r = races[key]
        assert abs(sum(r["cutoff_wins"].values()) - 1) < 1e-3
        assert r["magic_number"] is not None
        for t in r["teams"]:  # winning next week never hurts your chances
            if t["next_if_win"] is not None and t["next_if_loss"] is not None:
                assert t["next_if_win"] >= t["next_if_loss"]
        assert {(g["a"], g["b"]) for g in r["next_week_games"]} == {(1, 4), (2, 3)}
    # the team that's best now is most likely to get the bye; the worst, least likely to make it
    assert max(races["bye"]["teams"], key=lambda t: t["p"])["id"] == 1
    assert min(po.values(), key=lambda t: t["p"])["id"] == 4


def test_no_bye_race_when_the_bracket_is_a_power_of_two():
    teams, schedule = _league()
    assert set(simulate(teams, schedule, [3, 4], sims=200, playoff_teams=2)["races"]) == {"last", "playoffs"}
    assert set(simulate(teams, schedule, [3, 4], sims=200)["races"]) == {"last"}
