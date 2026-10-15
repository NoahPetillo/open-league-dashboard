"""Shame streaks: every rule, runs that break or keep going, ties, and the honest gaps."""

from __future__ import annotations

import json
from collections import defaultdict
from types import SimpleNamespace

from league import streaks
from league.report import Lineups, WeekRoster

SLOTS = {"QB": 1, "RB": 1, "WR": 1, "TE": 1, "K": 1, "D/ST": 1}
POS = {"qb": "QB", "rb": "RB", "wr": "WR", "te": "TE", "k": "K", "dst": "D/ST"}
TEAMS = [{"id": 1, "name": "Alpha", "manager": "Jordan"},
         {"id": 2, "name": "Bravo", "manager": "Morgan"},
         {"id": 3, "name": "Charlie", "manager": "Chris"},
         {"id": 4, "name": "Delta", "manager": ""}]


def _pos(pid: str) -> str:
    return POS[pid.rstrip("0123456789")]


def _quiet(t: int):
    """A lineup nobody can complain about: no dud, nothing on the bench."""
    return {f"qb{t}": 20, f"rb{t}": 15, f"wr{t}": 12, f"te{t}": 8, f"k{t}": 6, f"dst{t}": 5}, {}


def _ctx(games, lineups=None, proj=None, late=None, reg_weeks=14):
    """A fake league from ``games`` = [(week, home, away, home score, away score)].

    lineups: {(week, team): (started {id: points}, bench {id: points})}; anyone else gets ``_quiet``.
        Player ids end in the team number (wr1), so two teams never share one.
    proj: {(week, team): total ESPN projection for that team's starters, or {id: projection}}.
    late: {(week, team): ids that team picked up after their game kicked off}.
    """
    lineups, proj, late = lineups or {}, proj or {}, late or {}
    last = max(g[0] for g in games)
    matchups = {w: [] for w in range(1, last + 1)}
    rosters, pts, projections = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for w, home, away, hs, as_ in games:
        matchups[w].append({"home": home, "away": away, "home_score": hs, "away_score": as_})
        for t, score in ((home, hs), (away, as_)):
            started, bench = lineups.get((w, t)) or _quiet(t)
            everyone = {**started, **bench}
            rosters[w][t] = WeekRoster({pid: (pid, _pos(pid)) for pid in everyone}, set(started), score)
            pts[w].update(everyone)
            want = proj.get((w, t))
            if isinstance(want, dict):
                projections[w].update(want)
            elif want is not None:
                first, *rest = started
                projections[w].update({first: want, **dict.fromkeys(rest, 0.0)})
    eligible = {pid: [_pos(pid), "BE"] for week in pts.values() for pid in week}
    return SimpleNamespace(
        weeks=list(range(1, last + 1)), reg_weeks=reg_weeks, matchups=matchups, rosters=dict(rosters),
        pts=dict(pts), proj=dict(projections), pos={pid: _pos(pid) for pid in eligible}, names={},
        lu=Lineups(dict(pts), eligible, SLOTS), teams=TEAMS,
        startable=lambda w, t: set(rosters[w][t].players) - late.get((w, t), set()))


def _build(*args, **kw) -> dict:
    out = streaks.build(_ctx(*args, **kw))
    assert out is not None
    return out


def _active(out: dict) -> dict[tuple[int, str], dict]:
    return {(a["team"], a["key"]): a for a in out["active"]}


def _records(out: dict, key: str) -> list[dict]:
    return [r for r in out["records"] if r["key"] == key]


def test_losses_break_on_a_win_and_on_a_tie():
    # Team 1 (home) vs team 2: L L W L tie L L. The tie does not extend the middle run.
    results = [(130, 140), (125, 150), (150, 120), (130, 135), (140, 140), (130, 140), (130, 135)]
    out = _build([(w, 1, 2, a, b) for w, (a, b) in enumerate(results, 1)])
    loss = _active(out)[(1, "loss")]
    assert (loss["length"], loss["since_week"]) == (2, 6)
    assert loss["detail"] == "Lost 130.0 to Morgan's 135.0"
    # Team 2's only loss was week 3, and a single loss is not a streak.
    assert (2, "loss") not in _active(out)
    # Team 1's longest run is 2 twice (weeks 1-2, weeks 6-7): it's listed once, with the latest.
    assert _records(out, "loss") == [
        {"key": "loss", "team": 1, "length": 2, "from_week": 6, "to_week": 7, "active": True}]


def test_a_finished_streak_is_a_record_but_not_active():
    # Team 1 scores under 120 in weeks 1-3, then recovers. Team 2 starts its own run in week 3.
    games = [(1, 1, 2, 110, 150), (2, 1, 2, 115, 150), (3, 1, 2, 119.99, 118), (4, 1, 2, 150, 118)]
    out = _build(games)
    assert (1, "under120") not in _active(out)
    assert _active(out)[(2, "under120")]["since_week"] == 3
    assert _records(out, "under120") == [
        {"key": "under120", "team": 1, "length": 3, "from_week": 1, "to_week": 3, "active": False}]
    assert out["teams"][0] == {"team": 1, "active": {}}


def test_a_bye_week_does_not_break_a_run():
    # Team 1 has no game in week 2: its played weeks are 1, 3, 4 and all three are losses.
    games = [(1, 1, 2, 130, 140), (2, 3, 4, 150, 140), (3, 1, 2, 130, 140), (4, 1, 2, 130, 140)]
    loss = _active(_build(games))[(1, "loss")]
    assert (loss["length"], loss["since_week"]) == (3, 1)


def test_under_100_shows_at_one_week_and_is_also_under_120():
    # Week 1: team 1 scores 99.99 (under 100), team 2 exactly 100.0 (under 120 only).
    out = _build([(1, 1, 2, 99.99, 100.0)])
    active = _active(out)
    # One decimal would print 99.99 as "100.0", which isn't under 100: the cents are kept.
    assert active[(1, "sub100")]["length"] == 1 and active[(1, "sub100")]["detail"] == "Scored 99.99"
    assert (2, "sub100") not in active
    assert (1, "under120") not in active  # a single week is below the minimum of 2
    kinds = {k["key"]: k for k in out["kinds"]}
    assert kinds["sub100"]["title"] == "Utter disgust" and kinds["sub100"]["min"] == 1
    assert kinds["under120"]["title"] == "Shameful" and kinds["under120"]["min"] == 2
    assert out["lowest_score"] == {"team": 1, "week": 1, "score": 99.99}
    # Next week it happens again, so the counter reads 2.
    again = _build([(1, 1, 2, 99.99, 100.0), (2, 1, 2, 90, 140)])
    assert _active(again)[(1, "sub100")]["length"] == 2
    assert _active(again)[(1, "under120")]["length"] == 2


def test_under_projection_needs_three_weeks_and_a_projection_for_every_starter():
    games = [(1, 1, 2, 125, 150), (2, 1, 2, 130, 150), (3, 1, 2, 118.6, 150)]
    full = {(1, 1): 131.2, (2, 1): 140, (3, 1): 131.2}

    def run(proj):
        return _active(_build(games, proj=proj)).get((1, "under_proj"))

    got = run(full)
    assert (got["length"], got["since_week"]) == (3, 1)
    assert got["detail"] == "Scored 118.6 vs ESPN's 131.2"
    # Team 2 has no projection at all, so it can't be "under" it, however low it scores.
    assert (2, "under_proj") not in _active(_build(games, proj=full))
    # Gaps are not guessed at: no projection that week, one starter without one, or a total of 0
    # each end the run. Matching the projection exactly is not "under" either.
    assert run({k: v for k, v in full.items() if k != (2, 1)}) is None
    assert run({**full, (2, 1): {"qb1": 140}}) is None
    assert run({**full, (2, 1): 0}) is None
    assert run({**full, (2, 1): 130}) is None
    # A hair under shows the cents, so "under" never reads as a tie.
    close = _active(_build([(w, 1, 2, 131.19, 150) for w in (1, 2, 3)], proj={(w, 1): 131.21 for w in (1, 2, 3)}))
    assert close[(1, "under_proj")]["detail"] == "Scored 131.19 vs ESPN's 131.21"


def _blunder_lineup(t: int, bench_pts: float = 30.0):
    """Team t starts a 3-point WR while a WR on its bench scores ``bench_pts``."""
    started = {f"qb{t}": 20, f"rb{t}": 15, f"wr{t}": 3, f"te{t}": 8, f"k{t}": 6, f"dst{t}": 5}
    return started, {f"wr{t}0": bench_pts}


def test_a_blunder_needs_15_points_and_a_player_the_team_could_start():
    games = [(w, 1, 2, 130, 125) for w in (1, 2, 3)]
    lineups = {(w, 1): _blunder_lineup(1) for w in (2, 3)}
    run = _active(_build(games, lineups))[(1, "blunder")]
    assert (run["length"], run["since_week"]) == (2, 2)
    assert run["detail"] == "Benched wr10 (30.0) for wr1 (3.0)"
    # In week 3 he was picked up after his game: nobody could have started him, so no blunder.
    late = _build(games, lineups, late={(3, 1): {"wr10"}})
    assert (1, "blunder") not in _active(late)
    # 17.99 over a 3-point starter is a 14.99 miss: not enough. 18 is exactly 15: enough.
    small = {(w, 1): _blunder_lineup(1, 17.99) for w in (2, 3)}
    assert (1, "blunder") not in _active(_build(games, small))
    edge = {(w, 1): _blunder_lineup(1, 18) for w in (2, 3)}
    assert _active(_build(games, edge))[(1, "blunder")]["length"] == 2


def test_a_dud_is_a_qb_rb_wr_or_te_starter_under_3_points():
    games = [(w, 1, 2, 130, 125) for w in (1, 2, 3)]

    def lineup(**changes):
        started, bench = _quiet(1)
        return {**started, **changes}, bench

    lineups = {
        (1, 1): lineup(k1=0, dst1=-1),             # a kicker and a defense don't count
        (2, 1): lineup(te1=2.9, wr1=1.5),          # two duds: the worse one is named
        (3, 1): lineup(rb1=2.99, te1=3.0),         # 3.0 on the nose is not under 3
    }
    out = _build(games, lineups)
    run = _active(out)[(1, "dud")]
    assert (run["length"], run["since_week"]) == (2, 2)
    assert run["detail"] == "Started rb1 (2.99)"  # the cents stay, so it doesn't read as 3.0
    # Repeat week 2's lineup in week 3: of its two duds the worse one (1.5) is the one named.
    again = _build(games, {**lineups, (3, 1): lineups[(2, 1)]})
    assert _active(again)[(1, "dud")]["detail"] == "Started wr1 (1.5)"
    # Only the kicker and defense scored low in week 1, and one dud week alone is not a streak.
    assert (1, "dud") not in _active(_build(games[:2], lineups))


def test_records_list_every_team_that_holds_the_longest_run():
    # Team 1 loses weeks 1-3 and then wins. Team 3 loses weeks 2-4 and is still losing.
    games = [(1, 1, 2, 130, 140), (1, 3, 4, 140, 130),
             (2, 1, 2, 130, 140), (2, 3, 4, 130, 140),
             (3, 1, 2, 130, 140), (3, 3, 4, 130, 140),
             (4, 1, 2, 140, 130), (4, 3, 4, 130, 140)]
    out = _build(games)
    assert _records(out, "loss") == [
        {"key": "loss", "team": 1, "length": 3, "from_week": 1, "to_week": 3, "active": False},
        {"key": "loss", "team": 3, "length": 3, "from_week": 2, "to_week": 4, "active": True}]
    active = _active(out)
    assert (1, "loss") not in active
    assert active[(3, "loss")]["length"] == 3 and active[(3, "loss")]["since_week"] == 2
    assert active[(3, "loss")]["detail"] == "Lost 130.0 to Delta's 140.0"  # no manager: team name
    # A kind nobody has a streak in has no record: the one-off loss by team 2 doesn't count.
    assert _records(out, "dud") == [] and _records(out, "under120") == []


def test_names_ending_in_s_get_a_bare_apostrophe():
    out = _build([(1, 3, 4, 130, 140), (2, 3, 4, 130, 140), (3, 4, 3, 130, 140), (4, 4, 3, 130, 140)])
    assert _active(out)[(4, "loss")]["detail"] == "Lost 130.0 to Chris' 140.0"


def test_only_regular_season_weeks_count():
    games = [(w, 1, 2, 130, 140) for w in (1, 2, 3)]
    out = _build(games, reg_weeks=2)
    assert out["through"] == 2 and _active(out)[(1, "loss")]["length"] == 2
    assert _build(games, reg_weeks=0)["through"] == 3  # season length unknown: every week counts


def test_lowest_score_and_every_team_that_played_is_listed():
    games = [(1, 1, 2, 130, 90.5), (1, 3, 4, 125, 140), (2, 1, 2, 128, 135), (2, 3, 4, 150, 101.25)]
    out = _build(games)
    assert out["lowest_score"] == {"team": 2, "week": 1, "score": 90.5}
    assert out["through"] == 2
    assert out["teams"] == [{"team": t, "active": {}} for t in (1, 2, 3, 4)]
    loser = _build([(1, 1, 2, 130, 140), (2, 1, 2, 130, 140)])
    assert {t["team"]: t["active"] for t in loser["teams"]} == {1: {"loss": 2}, 2: {}}


def test_output_shape_is_json_and_in_display_order():
    out = _build([(1, 1, 2, 90, 150), (2, 1, 2, 95, 150)])
    json.dumps(out)
    assert set(out) == {"through", "kinds", "active", "records", "teams", "lowest_score"}
    assert [k["key"] for k in out["kinds"]] == ["loss", "under120", "sub100", "blunder", "under_proj", "dud"]
    assert {k["key"]: k["min"] for k in out["kinds"]} == {
        "loss": 2, "under120": 2, "sub100": 1, "blunder": 2, "under_proj": 3, "dud": 2}
    assert all(set(k) == {"key", "title", "what", "min"} and k["what"].endswith(".") for k in out["kinds"])
    assert all(set(a) == {"team", "key", "length", "since_week", "detail"} for a in out["active"])
    assert all(set(r) == {"key", "team", "length", "from_week", "to_week", "active"} for r in out["records"])
    # Same order as the kinds list, then longest first.
    assert [a["key"] for a in out["active"] if a["team"] == 1] == ["loss", "under120", "sub100"]
    assert _active(out)[(1, "sub100")]["length"] == 2


def test_no_completed_games_gives_none():
    ctx = _ctx([(1, 1, 2, 130, 140)])
    ctx.weeks = []
    assert streaks.build(ctx) is None
    ctx = _ctx([(1, 1, 2, 130, 140)])
    ctx.matchups = {1: []}
    assert streaks.build(ctx) is None
