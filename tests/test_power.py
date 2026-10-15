"""Power rankings: the score formula, ties, rank changes and the blurb rules."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from league import power


def _ctx(weeks, reg_weeks=0):
    """weeks: one list of (home, away, home_score, away_score) games per completed week."""
    ids = sorted({t for games in weeks for g in games for t in g[:2]})
    matchups = {w: [{"home": h, "away": a, "home_score": hs, "away_score": as_} for h, a, hs, as_ in games]
                for w, games in enumerate(weeks, 1)}
    return SimpleNamespace(through=len(weeks), reg_weeks=reg_weeks, matchups=matchups,
                           teams=[{"id": i, "name": f"T{i}"} for i in ids])


def _week(out, k):
    return {r["team"]: r for r in out["weeks"][k - 1]["teams"]}


def _tables(ctx):
    season = power._read_season(ctx)
    return season, {k: power._week_table(season, k) for k in range(1, season.through + 1)}


def _texts(ctx, team, kind=None):
    season, tables = _tables(ctx)
    return [f.text for f in power._facts(season, tables, team) if kind in (None, f.kind)]


# Week 1 of a 4-team league: 1 beats 2 (150-100), 3 beats 4 (120-110).
WEEK1 = [(1, 2, 150, 100), (3, 4, 120, 110)]


def test_score_formula_on_a_four_team_league():
    out = power.build(_ctx([WEEK1]))
    w = _week(out, 1)
    # Team 1: all-play 3-0 (50) + form 100 (30) + 1-0 record (20) = 100.
    # Team 3: all-play 2-1 (33.3) + form 40 (12) + 1-0 record (20) = 65.3.
    # Team 4: all-play 1-2 (16.7) + form 20 (6) + 0-1 record (0) = 22.7.
    # Team 2: all-play 0-3, form 0, 0-1 record = 0.
    assert {t: w[t]["score"] for t in w} == {1: 100.0, 3: 65.3, 4: 22.7, 2: 0.0}
    assert [r["team"] for r in out["weeks"][0]["teams"]] == [1, 3, 4, 2]
    assert [r["rank"] for r in out["weeks"][0]["teams"]] == [1, 2, 3, 4]
    assert w[3]["allplay"] == "2-1" and w[3]["record"] == "1-0"
    assert w[3]["allplay_pct"] == pytest.approx(0.6667, abs=1e-4)
    assert w[3]["form_avg"] == 120 and w[3]["win_pct"] == 1.0


def test_power_score_weights():
    assert power.power_score(1.0, 100.0, 1.0) == 100
    assert power.power_score(0.0, 0.0, 0.0) == 0
    assert power.power_score(0.5, 50.0, 0.5) == pytest.approx(50)
    assert power.power_score(None, 50.0, None) == pytest.approx(50)  # nothing played = .500


def test_ties_count_half_in_all_play_and_the_actual_record():
    out = power.build(_ctx([[(1, 2, 100, 100), (3, 4, 150, 90)]]))
    w = _week(out, 1)
    # Teams 1 and 2 tied each other and split the other two games: all-play 1-1-1, record 0-0-1.
    assert w[1]["record"] == w[2]["record"] == "0-0-1"
    assert w[1]["allplay"] == "1-1-1" and w[1]["allplay_pct"] == 0.5
    assert w[1]["win_pct"] == 0.5
    assert w[1]["score"] == w[2]["score"] == 40.0
    assert [r["team"] for r in out["weeks"][0]["teams"]] == [3, 1, 2, 4]  # level on points: team id decides


def test_everyone_equal_gets_a_flat_50_and_ranks_by_id():
    out = power.build(_ctx([[(1, 2, 100, 100), (3, 4, 100, 100)]]))
    assert [(r["team"], r["score"]) for r in out["weeks"][0]["teams"]] == [(1, 50.0), (2, 50.0), (3, 50.0), (4, 50.0)]


def test_rank_changes_positive_means_moved_up_and_points_for_breaks_ties():
    week2 = [(1, 2, 100, 150), (3, 4, 110, 120)]
    out = power.build(_ctx([WEEK1, week2]))
    assert all(r["change"] is None for r in out["weeks"][0]["teams"])
    w1, w2 = _week(out, 1), _week(out, 2)
    assert [w1[t]["rank"] for t in (1, 2, 3, 4)] == [1, 4, 2, 3]
    # Every all-play record is level after two weeks; 1 & 2 share the better form.
    assert [r["team"] for r in out["weeks"][1]["teams"]] == [1, 2, 3, 4]
    assert {t: w2[t]["change"] for t in w2} == {1: 0, 2: 2, 3: -1, 4: -1}
    assert w2[1]["score"] == w2[2]["score"] == 65.0 and w2[3]["score"] == w2[4]["score"] == 35.0


def test_form_only_counts_the_last_three_weeks():
    weeks = [[(1, 2, 300, 100)], [(1, 2, 100, 100)], [(1, 2, 100, 100)], [(1, 2, 100, 100)]]
    out = power.build(_ctx(weeks))
    assert _week(out, 3)[1]["form_avg"] == pytest.approx(166.67)
    assert _week(out, 4)[1]["form_avg"] == 100.0  # the 300 has dropped out of the window


def test_no_completed_weeks_means_no_power_rankings():
    assert power.build(_ctx([])) is None
    assert power.build(SimpleNamespace(through=0, reg_weeks=14, matchups={}, teams=[])) is None


def test_output_is_json_and_stops_at_the_end_of_the_regular_season():
    out = power.build(_ctx([WEEK1, WEEK1, WEEK1], reg_weeks=2))
    assert [w["week"] for w in out["weeks"]] == [1, 2]
    assert out["method"] == power.METHOD
    assert {b["team"] for b in out["blurbs"]} == {1, 2, 3, 4}
    json.dumps(out)


# ── blurbs ─────────────────────────────────────────────────────────────────────
#            wk1               wk2               wk3
# team 1:  150 (W)           140 (W)           160 (W)     3-0, never the highest in week 3
# team 2:  100 (L)           100 (W)           110 (L)     lowest score of week 3
# team 3:  120 (W)           130 (L)           170 (W)     highest score of week 3
# team 4:  110 (L)            90 (L)           120 (L)     0-3
BLURB_LEAGUE = [WEEK1, [(1, 3, 140, 130), (2, 4, 100, 90)], [(1, 4, 160, 120), (2, 3, 110, 170)]]


def test_blurbs_cover_every_team_with_one_line_each():
    out = power.build(_ctx(BLURB_LEAGUE))
    assert [b["team"] for b in out["blurbs"]] == [r["team"] for r in out["weeks"][-1]["teams"]]
    assert all(b["text"] for b in out["blurbs"])


def test_highest_and_lowest_score_of_the_week():
    ctx = _ctx(BLURB_LEAGUE)
    assert _texts(ctx, 3)[0] == "Highest score of the week (170.0)"
    assert "Lowest score of the week (110.0)" in _texts(ctx, 2, "low")


def test_losing_with_a_top_score_and_winning_with_a_bottom_score():
    # Week 1 of eight teams: team 1 posts 150 but loses to 160 (3rd-highest, behind 160 and 170);
    # team 3 wins with 120 (3rd-lowest, above only 110 and 100).
    ctx = _ctx([[(1, 2, 150, 160), (3, 4, 120, 110), (5, 6, 130, 140), (7, 8, 100, 170)]])
    assert _texts(ctx, 1, "bad-beat") == ["Lost with the 3rd-highest score of the week (150.0)"]
    assert _texts(ctx, 3, "lucky-win") == ["Won with the 3rd-lowest score of the week (120.0)"]
    assert _texts(ctx, 5, "bad-beat") == []  # four teams scored more, so it's just a loss


def test_lowest_score_run_and_win_loss_streaks():
    weeks = [[(1, 2, 150, 100), (3, 4, 130, 120)], [(1, 2, 150, 100), (3, 4, 130, 120)],
             [(1, 2, 150, 100), (3, 4, 130, 120)], [(1, 2, 150, 100), (3, 4, 130, 120)]]
    ctx = _ctx(weeks)
    assert "Lowest score in the league four weeks running (100.0 this week)" in _texts(ctx, 2, "low")
    assert "Lost 4 straight" in _texts(ctx, 2, "streak")
    assert "Still winless at 0-4" in _texts(ctx, 2, "streak")
    assert "Won 4 straight" in _texts(ctx, 1, "streak")
    assert "Still unbeaten at 4-0" in _texts(ctx, 1, "streak")


def test_streak_breaks_on_a_tie():
    season = power._read_season(_ctx([[(1, 2, 100, 90)], [(1, 2, 100, 90)], [(1, 2, 90, 90)],
                                      [(1, 2, 100, 90)], [(1, 2, 100, 90)]]))
    assert power._streak(season, 1, 5) == ("W", 2)
    assert power._streak(season, 1, 3) == ("", 0)


def test_luck_when_the_record_beats_the_all_play():
    # Team 1 beats the weakest team every week while two teams outscore it.
    ctx = _ctx([[(1, 2, 100, 50), (3, 4, 150, 140)]] * 3)
    assert _texts(ctx, 1, "luck") == ["3-0 on a 3-6 all-play. Living on luck"]


def test_unlucky_team_is_called_out_with_its_real_numbers():
    # Team 4 scores 140 each week (2nd-best) and loses to the 150: 0-3 on a 6-3 all-play.
    ctx = _ctx([[(1, 2, 100, 50), (3, 4, 150, 140)]] * 3)
    assert _texts(ctx, 4, "luck") == ["0-3 on a 6-3 all-play. The schedule has been cruel"]


def test_drought_names_the_week_and_a_round_number():
    ctx = _ctx([[(1, 2, 140, 90)], [(1, 2, 100, 90)], [(1, 2, 105, 90)], [(1, 2, 110, 90)]])
    assert "Hasn't cracked 120 since week 1" in _texts(ctx, 1, "drought")
    # The mark sits just above the best score since: 125 since week 1 means "hasn't cracked 130"...
    assert _texts(_ctx([[(1, 2, 140, 90)], [(1, 2, 100, 90)], [(1, 2, 125, 90)]]), 1, "drought") == [
        "Hasn't cracked 130 since week 1"]
    # ...and a team that just had its best week has no drought at all.
    assert _texts(_ctx([[(1, 2, 140, 90)], [(1, 2, 100, 90)], [(1, 2, 150, 90)]]), 1, "drought") == []


def test_rank_jump_blurb_quotes_the_score_and_the_spots():
    ctx = _ctx([WEEK1, [(1, 2, 100, 150), (3, 4, 110, 120)]])
    assert _texts(ctx, 2, "move") == ["Up 2 spots after dropping 150.0"]
    assert _texts(ctx, 3, "move") == []  # down one spot isn't worth a line


def test_a_kind_of_blurb_is_shared_by_at_most_the_cap(monkeypatch):
    season, tables = _tables(_ctx(BLURB_LEAGUE))
    monkeypatch.setattr(power, "_facts", lambda _s, _t, team: [power._Fact("x", 100 - team, f"x{team}"),
                                                              power._Fact("y", 1, f"y{team}")])
    picked = {b["team"]: b["text"] for b in power._blurbs(season, tables)}
    # Teams 1 and 2 had the best "x" facts and keep them; the cap pushes 3 and 4 to their next-best.
    assert picked == {1: "x1", 2: "x2", 3: "y3", 4: "y4"}


def test_blurb_numbers_round_like_the_site():
    assert power._f1(150.25) == "150.3" and power._f1(0.04) == "0.0" and power._f1(99.96) == "100.0"
    assert power._ordinal(2) == "2nd" and power._ordinal(11) == "11th" and power._ordinal(23) == "23rd"
