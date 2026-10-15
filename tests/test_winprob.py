"""Win probability: the normal model, slates and their labels, banking per checkpoint, the
headlines and the live (week in progress) version."""

from __future__ import annotations

import json
import math
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from league import winprob as wp
from league.report import WeekRoster

NY = ZoneInfo("America/New_York")


def ms(y, mo, d, h, mi=0):
    """Epoch ms of a New York wall-clock time (DST handled by zoneinfo, like the real kickoffs)."""
    return int(datetime(y, mo, d, h, mi, tzinfo=NY).timestamp() * 1000)


def utc_ms(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo("UTC")).timestamp() * 1000)


def cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# ── the model ──────────────────────────────────────────────────────────────────
def test_phi_is_a_normal_cdf():
    assert wp.phi(0) == 0.5
    assert wp.phi(1.96) == pytest.approx(0.975, abs=1e-4)
    assert wp.phi(-1.3) + wp.phi(1.3) == pytest.approx(1.0)


def test_equal_teams_are_a_coin_flip_and_the_odds_are_symmetric():
    assert wp.win_prob(100, 400, 100, 400) == 0.5
    a, b = wp.win_prob(120, 300, 100, 500), wp.win_prob(100, 500, 120, 300)
    assert a + b == pytest.approx(1.0)
    assert a == pytest.approx(cdf(20 / math.sqrt(800)))
    assert wp.win_prob(120, 300, 100, 500) > wp.win_prob(110, 300, 100, 500) > 0.5


def test_no_spread_means_it_is_decided_by_the_sign():
    assert wp.win_prob(101, 0, 100, 0) == 1.0
    assert wp.win_prob(99.5, 0, 100, 0) == 0.0
    assert wp.win_prob(100, 0, 100, 0) == 0.5
    assert wp.win_prob(100.0000000001, 0, 100, 0) == 0.5  # float noise is not a lead
    assert 0.5 < wp.win_prob(101, 0, 100, 25) < 1  # one side still has spread: a normal curve


def test_sd_table():
    for pos in ("QB", "RB", "WR", "TE"):
        assert wp.sd_of(pos, 20) == pytest.approx(3 + 0.35 * 20)
    assert wp.sd_of("WR", 10) == pytest.approx(6.5)
    assert wp.sd_of("K", 8.2) == 5.7 and wp.sd_of("K", 1) == 5.7
    assert wp.sd_of("HC", 9) == 4.5
    for pos in ("LB", "DE", "DT", "S", "CB", "D/ST", "P", "DL", "?"):
        assert wp.sd_of(pos, 7.5) == 3.0
    assert wp.sd_of("WR", -2.0) == 3.0  # a negative projection never narrows the spread


def test_a_starter_projected_exactly_zero_has_no_spread():
    for pos in ("QB", "RB", "WR", "TE", "K", "HC", "LB", "D/ST", "?"):
        assert wp.sd_of(pos, 0) == 0.0
        assert wp.sd_of(pos, 0.0) == 0.0


# ── slates ─────────────────────────────────────────────────────────────────────
# A realistic week (New York time): Thu 20:15, Sun 9:30, 13:00, 16:05 + 16:25, 20:20, Mon 19:15 + 20:15.
WEEK = [ms(2026, 10, 8, 20, 15), ms(2026, 10, 11, 9, 30), ms(2026, 10, 11, 13), ms(2026, 10, 11, 16, 5),
        ms(2026, 10, 11, 16, 25), ms(2026, 10, 11, 20, 20), ms(2026, 10, 12, 19, 15),
        ms(2026, 10, 12, 20, 15)]


def test_a_realistic_week_clusters_into_six_slates():
    firsts = wp.slate_starts(WEEK)
    assert firsts == [WEEK[0], WEEK[1], WEEK[2], WEEK[3], WEEK[5], WEEK[6]]
    assert wp.slate_names(firsts) == ["Thursday night", "the Sunday morning game", "the early games",
                                      "the late games", "Sunday night", "Monday night"]
    # every kickoff lands in its own slate: 4:25 with 4:05, 8:15 with 7:15
    assert [wp.slate_of(firsts, k) for k in WEEK] == [0, 1, 2, 3, 3, 4, 5, 5]


def test_duplicates_and_order_do_not_matter():
    assert wp.slate_starts(reversed(WEEK + WEEK)) == wp.slate_starts(WEEK)
    assert wp.slate_starts([]) == []


def test_a_slate_is_measured_from_its_first_kickoff_not_the_last():
    one = ms(2026, 10, 11, 13)
    two_hours = one + 2 * 3600 * 1000
    assert wp.slate_starts([one, one + 3600 * 1000, two_hours]) == [one]  # exactly 2 hours is still one slate
    assert wp.slate_starts([one, two_hours + 1]) == [one, two_hours + 1]
    # 1:00, 2:30 and 3:30 are NOT one chain: 3:30 is 2.5 hours after the slate's first kickoff
    assert wp.slate_starts([one, one + 90 * 60000, one + 150 * 60000]) == [one, one + 150 * 60000]


def test_a_starter_with_no_game_has_no_slate():
    firsts = wp.slate_starts(WEEK)
    assert wp.slate_of(firsts, None) is None
    assert wp.slate_of([], ms(2026, 10, 11, 13)) is None


@pytest.mark.parametrize("when, label", [
    ((2026, 10, 11, 9, 30), "the Sunday morning game"),
    ((2026, 10, 11, 11, 59), "the Sunday morning game"),
    ((2026, 10, 11, 12, 0), "the early games"),
    ((2026, 10, 11, 15, 59), "the early games"),
    ((2026, 10, 11, 16, 0), "the late games"),
    ((2026, 10, 11, 18, 59), "the late games"),
    ((2026, 10, 11, 19, 0), "Sunday night"),
    ((2026, 10, 11, 20, 20), "Sunday night"),
    ((2026, 10, 8, 20, 15), "Thursday night"),
    ((2026, 10, 12, 19, 15), "Monday night"),
    ((2026, 9, 9, 20, 20), "Wednesday night"),
    ((2026, 12, 19, 16, 30), "Saturday afternoon"),   # late-season Saturday doubleheader
    ((2026, 11, 27, 15, 0), "Friday afternoon"),      # Black Friday
    ((2026, 11, 27, 18, 59), "Friday afternoon"),
    ((2026, 11, 27, 19, 0), "Friday night"),
])
def test_slate_labels(when, label):
    assert wp.slate_label(ms(*when)) == label


def test_labels_are_the_same_either_side_of_the_clocks_changing():
    # Real epoch times (UTC), so the label has to follow New York's clock: EDT in October, EST in December.
    assert wp.slate_label(utc_ms(2026, 10, 11, 17)) == "the early games"       # 1:00 pm EDT
    assert wp.slate_label(utc_ms(2026, 12, 6, 18)) == "the early games"        # 1:00 pm EST
    assert wp.slate_label(utc_ms(2026, 10, 11, 15, 59)) == "the Sunday morning game"   # 11:59 am EDT
    assert wp.slate_label(utc_ms(2026, 10, 11, 16, 0)) == "the early games"            # 12:00 pm EDT
    assert wp.slate_label(utc_ms(2026, 12, 6, 16, 59)) == "the Sunday morning game"    # 11:59 am EST
    assert wp.slate_label(utc_ms(2026, 12, 6, 17, 0)) == "the early games"             # 12:00 pm EST
    assert wp.slate_label(utc_ms(2026, 10, 9, 0, 15)) == "Thursday night"      # 8:15 pm EDT, already Friday in UTC
    assert wp.slate_label(utc_ms(2026, 12, 11, 1, 15)) == "Thursday night"     # 8:15 pm EST, already Friday in UTC
    assert wp.slate_label(utc_ms(2026, 11, 2, 0, 15)) == "Sunday night"        # the night the clocks went back (Nov 1)
    assert wp.slate_label(utc_ms(2026, 11, 1, 18, 0)) == "the early games"     # Nov 1, 1:00 pm EST


def test_two_slates_with_the_same_name_get_their_kickoff_time():
    # Thanksgiving: three Thursday games, the first two both "afternoon".
    firsts = [ms(2026, 11, 26, 12, 30), ms(2026, 11, 26, 16, 30), ms(2026, 11, 26, 20, 20)]
    assert wp.slate_names(firsts) == ["Thursday afternoon (12:30 ET)", "Thursday afternoon (4:30 ET)",
                                      "Thursday night"]


# ── banking per checkpoint, on a week small enough to do by hand ───────────────
THU, SUN, MON = ms(2026, 10, 8, 20, 15), ms(2026, 10, 11, 13), ms(2026, 10, 12, 20, 15)


def lineup(prefix, rows):
    """rows: (position, projection, points, kickoff) → {id: (position, proj, pts, kick)} for ids prefix1, prefix2..."""
    return {f"{prefix}{i}": row for i, row in enumerate(rows, 1)}


def ctx_for(games, week=1):
    """games: [(home, away, home_lineup, away_lineup, home_score, away_score)] → a ReportContext look-alike.
    Scores default to the sum of the starters' points."""
    rosters, pts, proj, kick, pos, matchups = {}, {}, {}, {}, {}, []
    for home, away, hl, al, hs, as_ in games:
        for team, lu in ((home, hl), (away, al)):
            players = {pid: (pid, row[0]) for pid, row in lu.items()}
            total = round(sum(row[2] for row in lu.values()), 2)
            score = hs if team == home else as_
            rosters[team] = WeekRoster(players, set(lu), total if score is None else score)
            for pid, (p, pj, pt, k) in lu.items():
                pos[pid], proj[pid], pts[pid] = p, pj, pt
                if k is not None:
                    kick[pid] = k
        matchups.append({"home": home, "away": away, "home_score": rosters[home].score,
                         "away_score": rosters[away].score})
    return SimpleNamespace(weeks=[week], rosters={week: rosters}, pts={week: pts}, proj={week: proj},
                           kickoff={week: kick}, pos=pos, matchups={week: matchups})


# Team 1: QB Thu (proj 20, scored 30), WR Sun (10, 5), RB Mon (15, 12).  Team 2: QB Thu (18, 10),
# WR Sun (12, 20), RB Mon (10, 25).  Team 2 wins 55-47 after being 5% to win after Thursday night.
HOME = lineup("a", [("QB", 20, 30, THU), ("WR", 10, 5, SUN), ("RB", 15, 12, MON)])
AWAY = lineup("b", [("QB", 18, 10, THU), ("WR", 12, 20, SUN), ("RB", 10, 25, MON)])


def one_game():
    return wp.build(ctx_for([(1, 2, HOME, AWAY, None, None)]))


def test_checkpoints_follow_the_slates_and_end_with_final():
    (week,) = one_game()["weeks"]
    assert week["week"] == 1
    assert week["checkpoints"] == [{"label": "Before kickoff"},
                                   {"label": "After Thursday night", "slate": "Thursday night"},
                                   {"label": "After the early games", "slate": "the early games"},
                                   {"label": "Final", "slate": "Monday night"}]
    (game,) = week["games"]
    assert all(len(game[k]) == 4 for k in ("p_home", "home_pts", "away_pts", "home_mu", "away_mu"))


def test_points_are_banked_slate_by_slate_and_the_rest_stays_projected():
    (game,) = one_game()["weeks"][0]["games"]
    assert (game["home"], game["away"]) == (1, 2)
    assert game["home_pts"] == [0, 30, 35, 47]
    assert game["away_pts"] == [0, 10, 30, 55]
    assert game["home_mu"] == [45, 55, 50, 47]        # banked + projections still to play
    assert game["away_mu"] == [40, 32, 40, 55]


def test_win_chance_at_each_checkpoint_comes_from_the_normal_model():
    (game,) = one_game()["weeks"][0]["games"]
    var1 = [(3 + .35 * 20) ** 2 + (3 + .35 * 10) ** 2 + (3 + .35 * 15) ** 2,   # all three still to play
            (3 + .35 * 10) ** 2 + (3 + .35 * 15) ** 2,                           # the QB is banked
            (3 + .35 * 15) ** 2]                                                 # QB and WR banked
    var2 = [(3 + .35 * 18) ** 2 + (3 + .35 * 12) ** 2 + (3 + .35 * 10) ** 2,
            (3 + .35 * 12) ** 2 + (3 + .35 * 10) ** 2,
            (3 + .35 * 10) ** 2]
    mu1, mu2 = [45, 55, 50], [40, 32, 40]
    want = [round(cdf((a - b) / math.sqrt(x + y)), 4) for a, b, x, y in zip(mu1, mu2, var1, var2, strict=True)]
    assert want[0] == pytest.approx(0.5998, abs=1e-4) and want[1] == pytest.approx(0.9462, abs=1e-4)
    assert game["p_home"][:3] == want
    assert game["p_home"][3] == 0.0  # Final: team 2 won 55-47


def test_final_is_one_zero_or_half_whatever_the_odds_were():
    lone = lambda who, pj, pt: lineup(who, [("WR", pj, pt, THU), ("RB", 10, 10, MON)])  # noqa: E731
    out = wp.build(ctx_for([(1, 2, lone("a", 30, 5), lone("b", 5, 40), None, None),   # the favorite loses
                            (3, 4, lone("c", 5, 40), lone("d", 5, 40), None, None),   # dead level: a tie
                            (5, 6, lone("e", 5, 50), lone("f", 30, 5), None, None)]))  # the underdog wins
    p = [g["p_home"] for g in out["weeks"][0]["games"]]
    assert [x[-1] for x in p] == [0.0, 0.5, 1.0]
    assert p[0][0] > 0.5 > p[0][-1]  # the favorite lost, and it shows


def test_a_game_that_is_not_over_is_never_zero_or_one_percent():
    assert wp._chance(1000, 1, 0, 1) == 0.9999 and wp._chance(0, 1, 1000, 1) == 0.0001
    assert wp._chance(1, 0, 0, 0) == 1.0 and wp._chance(0, 0, 1, 0) == 0.0  # no spread at all: certain
    big = lineup("a", [("WR", 20, 80, THU), ("RB", 10, 10, MON)])
    small = lineup("b", [("WR", 20, 0, THU), ("RB", 5, 5, MON)])
    game = wp.build(ctx_for([(1, 2, big, small, None, None)]))["weeks"][0]["games"][0]
    # 80 banked against 0 with 10 and 5 still to play: z is above 10, but one Monday game is still to come.
    assert game["p_home"][1] == 0.9999 and game["p_home"][2] == 1.0


def test_projected_zero_starters_add_no_spread():
    # Team 1's Monday RB is out (projected 0): after Thursday only the opponent's Monday RB can still move things.
    h = lineup("a", [("QB", 20, 30, THU), ("RB", 0, 0, MON)])
    a = lineup("b", [("QB", 20, 10, THU), ("RB", 10, 8, MON)])
    game = wp.build(ctx_for([(1, 2, h, a, None, None)]))["weeks"][0]["games"][0]
    sd_b = 3 + 0.35 * 10
    assert game["p_home"][1] == round(cdf((30 - (10 + 10)) / sd_b), 4)
    # ... and with nothing left on either side the banked lead is simply the answer.
    h2 = lineup("a", [("QB", 20, 30, THU), ("RB", 0, 0, MON)])
    a2 = lineup("b", [("QB", 20, 10, THU), ("RB", 0, 0, MON)])
    game = wp.build(ctx_for([(1, 2, h2, a2, None, None)]))["weeks"][0]["games"][0]
    assert game["p_home"] == [0.5, 1.0, 1.0]  # level before kickoff; 20 points up with no one left to play


def test_a_starter_on_bye_counts_nothing_anywhere():
    h = lineup("a", [("QB", 20, 30, THU), ("WR", 0, 0, None)])
    a = lineup("b", [("QB", 20, 10, THU), ("WR", 0, 0, None)])
    game = wp.build(ctx_for([(1, 2, h, a, None, None)]))["weeks"][0]["games"][0]
    assert game["home_mu"] == [20, 30] and game["home_pts"] == [0, 30]
    assert game["p_home"][-1] == 1.0


def test_a_lineup_with_no_projections_gets_no_odds():
    h = lineup("a", [("QB", 0, 30, THU)])
    a = lineup("b", [("QB", 20, 10, THU)])
    assert wp.build(ctx_for([(1, 2, h, a, None, None)])) is None  # nothing to base odds on


def test_no_completed_weeks_means_no_recap():
    ctx = ctx_for([(1, 2, HOME, AWAY, None, None)])
    ctx.weeks = []
    assert wp.build(ctx) is None


def test_a_week_with_no_kickoff_times_is_one_slate():
    h = lineup("a", [("QB", 20, 30, None), ("WR", 10, 5, None)])
    a = lineup("b", [("QB", 18, 10, None), ("WR", 12, 20, None)])
    (week,) = wp.build(ctx_for([(1, 2, h, a, None, None)]))["weeks"]
    assert [c["label"] for c in week["checkpoints"]] == ["Before kickoff", "Final"]
    assert week["games"][0]["p_home"][1] == 1.0


def test_starters_points_that_miss_the_official_score_get_a_note_and_final_uses_the_official_score():
    out = wp.build(ctx_for([(1, 2, HOME, AWAY, 50.0, 55.0)]))  # starters add to 47.0, ESPN says 50.0
    game = out["weeks"][0]["games"][0]
    assert game["home_pts"][-1] == 50.0 and game["home_mu"][-1] == 50.0
    assert game["p_home"][-1] == 0.0
    assert "47.0" in game["note"] and "50.0" in game["note"]
    # within 0.05 is rounding, not a mismatch
    assert "note" not in wp.build(ctx_for([(1, 2, HOME, AWAY, 47.04, 55.0)]))["weeks"][0]["games"][0]
    assert "note" not in one_game()["weeks"][0]["games"][0]


def test_output_is_plain_json():
    out = one_game()
    assert json.loads(json.dumps(out)) == out
    assert out["model"]["sd"]["QB"] == [3.0, 0.35] and out["model"]["sd"]["K"] == [5.7, 0.0]
    assert out["model"]["method"]


# ── headlines ──────────────────────────────────────────────────────────────────
# Game A is the hand-worked game above (team 2 wins as a 40% underdog after being 5% to win).
# Game B: the favorite leads all week. Game C: a smaller upset (the 48% underdog wins).
B_HOME = lineup("c", [("QB", 20, 30, THU), ("WR", 10, 12, SUN), ("RB", 15, 20, MON)])
B_AWAY = lineup("d", [("QB", 10, 8, THU), ("WR", 10, 9, SUN), ("RB", 15, 10, MON)])
C_HOME = lineup("e", [("WR", 20, 10, THU), ("RB", 20, 10, MON)])
C_AWAY = lineup("f", [("WR", 19, 20, THU), ("RB", 19, 20, MON)])


def week_headlines():
    out = wp.build(ctx_for([(1, 2, HOME, AWAY, None, None), (3, 4, B_HOME, B_AWAY, None, None),
                            (5, 6, C_HOME, C_AWAY, None, None)]))
    return out, out["weeks"][0]["headlines"]


def test_comeback_is_the_winner_with_the_lowest_chance_before_final():
    _, h = week_headlines()
    c = h["comeback"]
    assert (c["team"], c["opp"], c["at"]) == (2, 1, 1)             # after Thursday night
    assert c["low"] == pytest.approx(0.0538, abs=1e-4)
    assert (c["score"], c["opp_score"]) == (55.0, 47.0)


def test_collapse_is_the_loser_with_the_highest_chance_before_final():
    _, h = week_headlines()
    c = h["collapse"]
    assert (c["team"], c["opp"], c["at"]) == (1, 2, 1)
    assert c["high"] == pytest.approx(0.9462, abs=1e-4)
    assert (c["score"], c["opp_score"]) == (47.0, 55.0)


def test_swing_is_the_biggest_single_move_and_goes_to_the_team_that_gained():
    out, h = week_headlines()
    s = h["swing"]
    # Game A's last step: team 1 was 83% before Monday night and lost, so team 2 went from 17% to 100%.
    assert (s["team"], s["opp"], s["at"]) == (2, 1, 3)
    assert s["from"] == pytest.approx(0.1705, abs=1e-4) and s["to"] == 1.0
    game = out["weeks"][0]["games"][0]
    assert s["from"] == pytest.approx(1 - game["p_home"][2], abs=1e-4)


def test_upset_is_the_pregame_underdog_who_won_with_the_lowest_chance():
    _, h = week_headlines()
    u = h["upset"]
    assert (u["team"], u["opp"]) == (2, 1)                 # not game C's 48% underdog
    assert u["pregame"] == pytest.approx(0.4002, abs=1e-4)
    assert (u["score"], u["opp_score"]) == (55.0, 47.0)


def test_a_week_where_every_favorite_led_all_week_has_no_comeback_collapse_or_upset():
    out = wp.build(ctx_for([(3, 4, B_HOME, B_AWAY, None, None)]))
    h = out["weeks"][0]["headlines"]
    assert h["comeback"] is None and h["collapse"] is None and h["upset"] is None
    assert h["swing"] is not None  # something always moves


def test_a_tied_game_has_no_winner_to_write_about():
    tie_home = lineup("a", [("QB", 20, 10, THU), ("RB", 15, 10, MON)])
    tie_away = lineup("b", [("QB", 10, 10, THU), ("RB", 25, 10, MON)])
    h = wp.build(ctx_for([(1, 2, tie_home, tie_away, None, None)]))["weeks"][0]["headlines"]
    assert h["comeback"] is None and h["collapse"] is None and h["upset"] is None


def test_favorites_record_counts_pregame_favorites_and_skips_ties_and_even_games():
    out, _ = week_headlines()
    assert out["favorites"] == {"won": 1, "lost": 2}   # B's favorite won; A's and C's lost
    even_h = lineup("a", [("QB", 20, 10, THU)])
    even_a = lineup("b", [("QB", 20, 30, THU)])
    tie_h = lineup("g", [("QB", 20, 10, THU), ("RB", 15, 10, MON)])
    tie_a = lineup("h", [("QB", 10, 10, THU), ("RB", 25, 10, MON)])  # projected level... and tied
    skipped = wp.build(ctx_for([(1, 2, even_h, even_a, None, None)]))
    assert skipped["favorites"] == {"won": 0, "lost": 0}  # level projections: nobody was the favorite
    tied = wp.build(ctx_for([(7, 8, tie_h, tie_a, None, None)]))
    assert tied["favorites"] == {"won": 0, "lost": 0}


# ── the week in progress ───────────────────────────────────────────────────────
def iso(kick):
    return None if kick is None else datetime.fromtimestamp(kick / 1000, NY).isoformat()


def live_side(team, lu, status, score=None):
    """lu: the same rows as the recap tests; status: {kickoff ms: status of the games kicking off then}."""
    starters = [{"id": pid, "name": pid, "pos": pos, "slot": pos, "team": "XXX", "points": pts, "projected": pj,
                 "status": "bye" if k is None else status[k], "kickoff": iso(k), "injury": None}
                for pid, (pos, pj, pts, k) in lu.items()]
    return {"team": team, "score": sum(s["points"] for s in starters) if score is None else score,
            "projected": sum(pj for _, pj, _, _ in lu.values()), "yet_to_play": 0, "playing": 0,
            "starters": starters, "bench": []}


def live_data(status, home=HOME, away=AWAY, scores=(None, None)):
    return {"week": 5, "generated_at": "2026-10-09T03:00:00+00:00",
            "matchups": [{"home": live_side(1, home, status, scores[0]), "away": live_side(2, away, status, scores[1])}]}


def test_live_pregame_uses_every_projection():
    out = wp.live(live_data({THU: "upcoming", SUN: "upcoming", MON: "upcoming"}))
    assert out["week"] == 5 and out["done"] is False
    (pre,) = out["pregame"]
    assert pre == {"home": 1, "away": 2, "p_home": pytest.approx(0.5998, abs=1e-4), "proj_home": 45.0,
                   "proj_away": 40.0}
    assert out["checkpoints"] == [{"label": "Before kickoff"}]
    assert out["headlines"] == {"swing": None, "upset_watch": None}


def test_live_with_one_slate_finished_and_the_rest_upcoming():
    out = wp.live(live_data({THU: "final", SUN: "upcoming", MON: "upcoming"}))
    assert [c["label"] for c in out["checkpoints"]] == ["Before kickoff", "After Thursday night"]
    assert out["done"] is False
    (game,) = out["games"]
    assert game["home_pts"] == [0, 30] and game["away_pts"] == [0, 10]
    assert game["home_mu"] == [45, 55] and game["away_mu"] == [40, 32]
    assert game["p_home"][0] == out["pregame"][0]["p_home"]
    assert game["p_home"][1] == pytest.approx(0.9462, abs=1e-4)
    s = out["headlines"]["swing"]
    assert (s["team"], s["opp"], s["at"]) == (1, 2, 1)
    assert s["from"] == pytest.approx(0.5998, abs=1e-4) and s["to"] == pytest.approx(0.9462, abs=1e-4)
    assert out["headlines"]["upset_watch"] is None   # the favorite is the one pulling away


def test_live_points_from_games_still_going_are_never_banked():
    # A WR in the Sunday slate has 7 points so far and is "live": he still counts as his 10-point projection.
    home = {**HOME, "a2": ("WR", 10, 7, SUN)}
    out = wp.live(live_data({THU: "final", SUN: "live", MON: "upcoming"}, home=home))
    assert [c["label"] for c in out["checkpoints"]] == ["Before kickoff", "After Thursday night"]
    (game,) = out["games"]
    assert game["home_pts"] == [0, 30] and game["home_mu"] == [45, 55]


def test_live_slates_complete_in_order_so_a_live_game_holds_back_the_ones_after_it():
    out = wp.live(live_data({THU: "live", SUN: "final", MON: "upcoming"}))
    assert [c["label"] for c in out["checkpoints"]] == ["Before kickoff"]


def test_live_upset_watch_is_a_pregame_underdog_who_is_now_ahead():
    away = {**AWAY, "b1": ("QB", 18, 40, THU)}
    home = {**HOME, "a1": ("QB", 20, 5, THU)}
    out = wp.live(live_data({THU: "final", SUN: "upcoming", MON: "upcoming"}, home=home, away=away))
    w = out["headlines"]["upset_watch"]
    assert (w["team"], w["opp"], w["at"]) == (2, 1, 1)
    assert w["pregame"] == pytest.approx(0.4002, abs=1e-4) and w["now"] > 0.9
    s = out["headlines"]["swing"]
    assert s["team"] == 2 and s["from"] == w["pregame"]


def test_live_underdog_still_behind_is_not_an_upset_watch():
    away = {**AWAY, "b1": ("QB", 18, 12, THU)}
    home = {**HOME, "a1": ("QB", 20, 10, THU)}   # 10 vs 12 banked: still close, the favorite stays ahead
    out = wp.live(live_data({THU: "final", SUN: "upcoming", MON: "upcoming"}, home=home, away=away))
    assert out["headlines"]["upset_watch"] is None


def test_live_when_everything_is_final_ends_in_final_with_the_official_scores():
    out = wp.live(live_data({THU: "final", SUN: "final", MON: "final"}, scores=(47.0, 55.0)))
    assert out["done"] is True
    assert [c["label"] for c in out["checkpoints"]] == ["Before kickoff", "After Thursday night",
                                                       "After the early games", "Final"]
    assert out["checkpoints"][-1]["slate"] == "Monday night"
    (game,) = out["games"]
    assert game["p_home"][-1] == 0.0 and game["home_pts"][-1] == 47.0
    assert out["headlines"]["upset_watch"]["team"] == 2 and out["headlines"]["upset_watch"]["now"] == 1.0
    assert "note" not in game


def test_live_without_a_single_kickoff_time_still_gets_pregame_odds():
    nokick = lambda lu: {pid: (pos, pj, pts, None) for pid, (pos, pj, pts, _) in lu.items()}  # noqa: E731
    data = live_data({}, home=nokick(HOME), away=nokick(AWAY))
    for side in ("home", "away"):
        for s in data["matchups"][0][side]["starters"]:
            s["status"] = "upcoming"
    out = wp.live(data)
    assert out["checkpoints"] == [] and out["games"] == [] and out["done"] is False
    assert out["pregame"][0]["p_home"] == pytest.approx(0.5998, abs=1e-4)


def test_live_has_nothing_to_say_without_matchups_or_projections():
    assert wp.live({"week": 5, "matchups": []}) is None
    flat = {pid: (pos, 0, 0, k) for pid, (pos, _, _, k) in HOME.items()}
    out = wp.live(live_data({THU: "upcoming", SUN: "upcoming", MON: "upcoming"}, home=flat))
    assert out["pregame"] == [] and out["games"] == []


def test_live_output_is_plain_json():
    out = wp.live(live_data({THU: "final", SUN: "upcoming", MON: "upcoming"}))
    assert json.loads(json.dumps(out)) == out


def test_live_kickoffs_without_a_time_zone_are_read_as_new_york_time():
    assert wp._iso_ms("2026-10-11T13:00:00") == ms(2026, 10, 11, 13)
    assert wp._iso_ms("2026-10-11T13:00:00-04:00") == ms(2026, 10, 11, 13)
    assert wp._iso_ms(None) is None and wp._iso_ms("soon") is None
