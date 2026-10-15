"""Build the league dashboard dataset from ESPN (read-only).

Everything the site shows comes out of three ESPN reads: team standings, each
completed week's box scores (rosters, lineup slots, exact league-scored points),
and the full activity feed (trades, adds, drops, FAAB bids).

Trade grading — "what did this trade do to your starting lineup?"
    For every week after a trade lands, compare the best possible starting lineup
    from the roster the team ACTUALLY had against the best lineup from the roster
    it WOULD have had without the trade (received players out, sent players back
    in). Both sides use the same hindsight-optimal lineup rule, so the number
    isolates the trade itself rather than anyone's start/sit calls. The sum over
    weeks is the trade's net lineup points for that team.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from league.espn import EspnClient
from league.lineup import best_lineup

log = logging.getLogger(__name__)

NON_STARTING = {"BE", "IR"}


@dataclass
class WeekRoster:
    players: dict[str, tuple[str, str]]  # espn_id -> (name, position)
    started: set[str]
    score: float


def _team_id(team) -> int | None:
    tid = getattr(team, "team_id", None)
    return int(tid) if tid is not None else None


@dataclass
class Lineups:
    """Week-by-week points + ESPN slot eligibility → best possible lineup totals."""
    pts: dict[int, dict[str, float]]
    eligible: dict[str, list[str]]
    slots: dict[str, int]

    def best(self, ids, week: int) -> float:
        return best_lineup(self.pts[week], self.eligible, ids, self.slots)[0]


# ── ESPN reads ─────────────────────────────────────────────────────────────────
@dataclass
class WeekReads:
    """Everything ``_read_weeks`` pulls out of the completed weeks' box scores."""
    rosters: dict[int, dict[int, WeekRoster]]   # week → team → roster that week
    pts: dict[int, dict[str, float]]             # week → player id → league points
    pos: dict[str, str]                          # player id → position
    eligible: dict[str, list[str]]               # player id → ESPN lineup slots he can fill
    matchups: dict[int, list[dict]]              # week → [{home, away, home_score, away_score}]
    pro: dict[str, str]                          # player id → NFL team abbreviation
    kicks: dict[int, tuple[int, int]]            # week → (first, last) kickoff, epoch ms
    proj: dict[int, dict[str, float]]            # week → player id → ESPN's pregame projection
    kickoff: dict[int, dict[str, int]]           # week → player id → his game's kickoff, epoch ms


def _read_weeks(lg, through: int) -> WeekReads:
    """One box-score read per completed week (see ``WeekReads``). Projections and kickoffs
    cover every rostered player, bench included; a player on bye has no kickoff."""
    rosters: dict[int, dict[int, WeekRoster]] = {}
    pts: dict[int, dict[str, float]] = defaultdict(dict)
    proj: dict[int, dict[str, float]] = defaultdict(dict)
    kickoff: dict[int, dict[str, int]] = defaultdict(dict)
    pos: dict[str, str] = {}
    eligible: dict[str, list[str]] = {}
    matchups: dict[int, list[dict]] = {}
    pro: dict[str, str] = {}
    kicks: dict[int, tuple[int, int]] = {}
    for w in range(1, through + 1):
        rosters[w], matchups[w] = {}, []
        for m in lg.box_scores(w):
            sides = []
            for team, score, lineup in ((m.home_team, m.home_score, m.home_lineup),
                                        (m.away_team, m.away_score, m.away_lineup)):
                tid = _team_id(team)
                if tid is None:
                    continue
                players, started = {}, set()
                for bp in lineup or []:
                    eid = str(bp.playerId)
                    players[eid] = (bp.name, bp.position)
                    pos[eid] = bp.position
                    pro[eid] = getattr(bp, "proTeam", None) or pro.get(eid, "")
                    kick = getattr(bp, "game_date", None)
                    if kick is not None:
                        ms = int(kick.timestamp() * 1000)
                        kickoff[w][eid] = ms
                        lo, hi = kicks.get(w, (ms, ms))
                        kicks[w] = (min(lo, ms), max(hi, ms))
                    eligible[eid] = list(getattr(bp, "eligibleSlots", None) or [])
                    pts[w][eid] = float(bp.points or 0.0)
                    proj[w][eid] = float(getattr(bp, "projected_points", 0.0) or 0.0)
                    if bp.slot_position not in NON_STARTING:
                        started.add(eid)
                rosters[w][tid] = WeekRoster(players, started, round(float(score or 0), 2))
                sides.append((tid, round(float(score or 0), 2)))
            if len(sides) == 2:
                matchups[w].append({"home": sides[0][0], "away": sides[1][0],
                                    "home_score": sides[0][1], "away_score": sides[1][1]})
    return WeekReads(rosters, pts, pos, eligible, matchups, pro, kicks, proj, kickoff)


ACQUIRED = {"FA ADDED", "WAIVER ADDED", "TRADE_RECEIVED"}
LET_GO = {"DROPPED", "TRADE_SENT"}
LATE_WINDOW_MS = 7 * 24 * 3600 * 1000  # a week's box-score roster can include moves up to waivers


def _late_adds(rosters, kickoff, activity: list[dict], draft: list[dict]) -> dict[int, dict[int, set[str]]]:
    """``late[week][team]``: players on a team's box-score roster that week who joined it
    only after their own game kicked off, so they couldn't have been in its lineup.

    Needs evidence: an add (or trade in) by that team within a week after the player's
    kickoff, with the team's last move for him before kickoff not an acquisition (the
    draft counts as one at time 0). Anything the feed can't explain is left startable."""
    events: dict[tuple[int, str], list[tuple[int, int]]] = defaultdict(list)
    for pick in draft:
        events[(pick["team"], pick["id"])].append((0, 1))
    for act in activity:
        for tid, kind, pid, _amount in act["moves"]:
            if tid is None:
                continue
            if kind in ACQUIRED:
                events[(int(tid), str(pid))].append((int(act["date"]), 1))
            elif kind in LET_GO:
                events[(int(tid), str(pid))].append((int(act["date"]), -1))
    late: dict[int, dict[int, set[str]]] = {}
    for w, by_team in rosters.items():
        for tid, roster in by_team.items():
            for pid in roster.players:
                k = kickoff.get(w, {}).get(pid)
                ev = sorted(events.get((tid, pid), []))
                if k is None or not ev:
                    continue
                joined_late = any(sign > 0 and k < d <= k + LATE_WINDOW_MS for d, sign in ev)
                before = [sign for d, sign in ev if d < k]
                if joined_late and (not before or before[-1] < 0):
                    late.setdefault(w, {}).setdefault(tid, set()).add(pid)
    return late


def _draft(lg) -> list[dict]:
    """Every draft pick in order: ``{pick, round, round_pick, team, id, name}``."""
    picks = []
    for p in getattr(lg, "draft", None) or []:
        team = _team_id(getattr(p, "team", None))
        if team is None or getattr(p, "playerId", None) is None:
            continue
        picks.append({"round": int(p.round_num), "round_pick": int(p.round_pick), "team": team,
                      "id": str(p.playerId), "name": getattr(p, "playerName", "") or ""})
    picks.sort(key=lambda p: (p["round"], p["round_pick"]))
    for i, p in enumerate(picks):
        p["pick"] = i + 1
    return [{"pick": p["pick"], **{k: v for k, v in p.items() if k != "pick"}} for p in picks]


def _backfill(cards: dict, weeks: list[int], pts, pos, eligible, pro) -> None:
    """Fill in players box scores don't cover — anyone who sat in free agency some
    week after being traded or dropped — from their ESPN player cards."""
    for eid, card in cards.items():
        pos.setdefault(eid, getattr(card, "position", "?"))
        pro.setdefault(eid, getattr(card, "proTeam", None) or "")
        eligible.setdefault(eid, list(getattr(card, "eligibleSlots", None) or []))
        for w in weeks:
            if eid not in pts[w]:
                pts[w][eid] = float((getattr(card, "stats", None) or {}).get(w, {}).get("points", 0.0) or 0.0)


# ── trades ─────────────────────────────────────────────────────────────────────
def _parse_trades(activity: list[dict], name_of) -> list[dict]:
    """Group each activity entry's trade moves into sides: team → players (and FAAB
    dollars) in/out."""
    trades = []
    for act in activity:
        sides: dict[int, dict] = {}
        for tid, kind, pid, amount in act["moves"]:
            if tid is None or kind not in ("TRADE_RECEIVED", "TRADE_SENT", "FAAB_RECEIVED", "FAAB_SENT"):
                continue
            side = sides.setdefault(int(tid), {"team": int(tid), "received": {}, "sent": {},
                                               "faab_received": 0, "faab_sent": 0})
            if kind == "TRADE_RECEIVED":
                side["received"][pid] = name_of(pid)
            elif kind == "TRADE_SENT":
                side["sent"][pid] = name_of(pid)
            elif kind == "FAAB_RECEIVED":
                side["faab_received"] += amount
            else:
                side["faab_sent"] += amount
        if len(sides) >= 2:
            trades.append({"date": act["date"], "sides": list(sides.values())})
    return sorted(trades, key=lambda t: t["date"])


def _effective_weeks(trades, rosters, weeks: list[int]) -> list[int | None]:
    """First completed week each trade shows up on a roster. Trades are chronological,
    so one whose players were flipped again before the next box score inherits the
    week of the next trade that IS visible; anything after the last box score is
    still pending."""
    seen = []
    for t in trades:
        found = None
        for w in weeks:
            if any(rosters[w].get(s["team"]) and set(s["received"]) & set(rosters[w][s["team"]].players)
                   for s in t["sides"]):
                found = w
                break
        seen.append(found)
    out, nxt = [None] * len(trades), None
    for i in range(len(trades) - 1, -1, -1):
        nxt = seen[i] if seen[i] is not None and (nxt is None or seen[i] <= nxt) else nxt
        out[i] = nxt
    return out


def _undo(ids: set[str], sides: list[dict]) -> set[str]:
    """Roster as if these trades (one team's sides, chronological) never happened."""
    for side in reversed(sides):
        ids = (ids - set(side["received"])) | set(side["sent"])
    return ids


def _trade_tree(idx: int, team: int, trades, effs) -> list[tuple[int, dict]]:
    """Trade ``idx`` plus every later trade this team made by flipping what it got
    (directly or down the chain) — without the first trade, those couldn't happen."""
    side = next(s for s in trades[idx]["sides"] if s["team"] == team)
    tree, assets = [(idx, side)], set(side["received"])
    for j in range(idx + 1, len(trades)):
        later = next((s for s in trades[j]["sides"] if s["team"] == team), None)
        if later and effs[j] is not None and assets & set(later["sent"]):
            tree.append((j, later))
            assets |= set(later["received"])
    return tree


def _grade_side(idx, side, trades, effs, rosters, lu: Lineups, pos, weeks) -> dict:
    team, eff = side["team"], effs[idx]
    tree = _trade_tree(idx, team, trades, effs)
    active_weeks = [w for w in weeks if eff is not None and w >= eff]
    weekly = []
    for w in active_weeks:
        roster = rosters[w].get(team)
        if roster is None:
            continue
        actual_ids = set(roster.players)
        without_ids = _undo(actual_ids, [s for j, s in tree if effs[j] <= w])
        with_trade = lu.best(actual_ids, w)
        without = lu.best(without_ids, w)
        weekly.append({"week": w, "with": round(with_trade, 2), "without": round(without, 2),
                       "delta": round(with_trade - without, 2)})

    def received():
        out = []
        pts = lu.pts
        for eid, name in side["received"].items():
            on = [w for w in active_weeks if eid in rosters[w].get(team, WeekRoster({}, set(), 0)).players]
            out.append({"id": eid, "name": name, "pos": pos.get(eid, "?"),
                        "points": round(sum(pts[w].get(eid, 0.0) for w in on), 2),
                        "started_points": round(sum(pts[w].get(eid, 0.0) for w in on
                                                    if eid in rosters[w][team].started), 2),
                        "weeks_rostered": len(on)})
        return sorted(out, key=lambda x: -x["points"])

    def sent():
        out = [{"id": eid, "name": name, "pos": pos.get(eid, "?"),
                "points": round(sum(lu.pts[w].get(eid, 0.0) for w in active_weeks), 2)}
               for eid, name in side["sent"].items()]
        return sorted(out, key=lambda x: -x["points"])

    return {"team": team, "received": received(), "sent": sent(), "weekly": weekly,
            "faab_received": side.get("faab_received", 0), "faab_sent": side.get("faab_sent", 0),
            "flipped_into": [trades[j]["id"] for j, _ in tree[1:]],
            "net": round(sum(x["delta"] for x in weekly), 2)}


def _team_trade_net(team, trades, effs, rosters, lu: Lineups, weeks) -> float:
    """Actual lineups vs. lineups had this team made none of its trades."""
    sides = [(j, s) for j, t in enumerate(trades) for s in t["sides"]
             if s["team"] == team and effs[j] is not None]
    total = 0.0
    for w in weeks:
        roster = rosters[w].get(team)
        active = [s for j, s in sides if effs[j] <= w]
        if roster is None or not active:
            continue
        actual = set(roster.players)
        total += lu.best(actual, w) - lu.best(_undo(actual, active), w)
    return round(total, 2)


def _most_traded(trades: list[dict], pts, pos, pro, weeks: list[int], top: int = 8) -> list[dict]:
    """Players passed around the most: trade count, then how many fantasy teams
    they've been on, then season points."""
    seen: dict[str, dict] = {}
    for t in trades:
        for side in t["sides"]:
            for pid, name in side["received"].items():
                p = seen.setdefault(pid, {"id": pid, "name": name, "trades": 0, "path": [],
                                          "first_date": t["date"]})
                if not p["path"]:
                    giver = next((s["team"] for s in t["sides"] if pid in s["sent"]), None)
                    if giver is not None:
                        p["path"].append(giver)
                p["trades"] += 1
                p["path"].append(side["team"])
                p["last_date"] = t["date"]
    out = []
    for p in seen.values():
        season = round(sum(pts[w].get(p["id"], 0.0) for w in weeks), 2)
        played = sum(1 for w in weeks if pts[w].get(p["id"], 0.0))
        out.append({**p, "pos": pos.get(p["id"], "?"), "pro_team": pro.get(p["id"], ""),
                    "teams": len(set(p["path"])), "owner": p["path"][-1],
                    "season_points": season,
                    "avg": round(season / played, 2) if played else 0.0})
    out.sort(key=lambda p: (-p["trades"], -p["teams"], -p["season_points"]))
    return out[:top]


# ── the report ─────────────────────────────────────────────────────────────────
@dataclass
class ReportContext:
    """Everything the feature modules (odds, awards, FAAB, power rankings, history)
    get to build their part of the report. Each one exposes ``build(ctx) -> dict``."""
    client: EspnClient
    lg: Any                                   # espn-api League
    season: int
    through: int                              # last completed week in the report
    current_week: int                         # ESPN's week in progress
    weeks: list[int]                          # completed weeks, 1..through
    reg_weeks: int                            # regular-season length
    playoff_teams: int
    rosters: dict[int, dict[int, WeekRoster]]  # week → team → roster that week
    pts: dict[int, dict[str, float]]          # week → player id → league points
    pos: dict[str, str]                       # player id → position
    pro: dict[str, str]                       # player id → NFL team abbreviation
    names: dict[str, str]                     # player id → name
    lu: Lineups                               # lu.best(player_ids, week) → best lineup total
    matchups: dict[int, list[dict]]           # week → [{home, away, home_score, away_score}]
    schedule: dict[int, list[tuple[int, int]]]  # every regular-season week → [(team, team)]
    divisions: dict[int, int]                 # team id → division id
    division_names: dict[int, str]
    kicks: dict[int, tuple[int, int]]         # week → (first, last) kickoff, epoch ms
    activity: list[dict]                      # EspnClient.transactions()
    trades: list[dict]                        # graded trades, as in the report
    teams: list[dict]                         # team rows, as in the report
    faab_budget: int
    counters: dict[int, dict] = field(default_factory=dict)  # ESPN transactionCounter per team
    proj: dict[int, dict[str, float]] = field(default_factory=dict)    # week → player → ESPN projection
    kickoff: dict[int, dict[str, int]] = field(default_factory=dict)   # week → player → kickoff, epoch ms
    late: dict[int, dict[int, set[str]]] = field(default_factory=dict)  # week → team → added after kickoff
    draft: list[dict] = field(default_factory=list)  # [{pick, round, round_pick, team, id, name}]
    outputs: dict[str, Any] = field(default_factory=dict)  # finished features' output, by report key

    def startable(self, week: int, team: int) -> set[str]:
        """Players on ``team``'s roster in ``week`` who could actually have been started:
        everyone except those it picked up after their game kicked off."""
        roster = self.rosters.get(week, {}).get(team)
        if roster is None:
            return set()
        return set(roster.players) - self.late.get(week, {}).get(team, set())


def _schedule(lg, reg_weeks: int) -> dict[int, list[tuple[int, int]]]:
    """Every regular-season matchup from ESPN's schedule (played or not)."""
    out: dict[int, list[tuple[int, int]]] = {}
    for t in lg.teams:
        for i, opp in enumerate(getattr(t, "schedule", []) or []):
            w, a, b = i + 1, t.team_id, getattr(opp, "team_id", None)
            if w <= reg_weeks and b is not None and a < b:
                out.setdefault(w, []).append((a, b))
    return out


def _feature(name: str, build, ctx: ReportContext):
    """A broken feature logs a warning and drops out instead of sinking the site."""
    try:
        return build(ctx)
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed (%s: %s); leaving it out.", name, type(e).__name__, e)
        return None


def build_context(client: EspnClient, through: int | None = None) -> ReportContext:
    """Read ESPN once and grade the trades: everything the feature modules build from.
    Handy on its own for checking one feature against real data without writing the site:
    ``ctx = build_context(EspnClient()); whatif.build(ctx)``."""
    lg = client.league()
    current = int(getattr(lg, "current_week", 1) or 1)
    # current_week is the week in progress; grade only finished weeks.
    last = max(through if through is not None else current - 1, 0)
    weeks = list(range(1, last + 1))

    reads = _read_weeks(lg, last)
    rosters, pts, pos, eligible, matchups, pro, kicks = (
        reads.rosters, reads.pts, reads.pos, reads.eligible, reads.matchups, reads.pro, reads.kicks)
    try:
        activity = client.transactions()
    except Exception as e:  # noqa: BLE001
        # A public league's scores can be readable while its activity feed isn't: ESPN only
        # shows adds, drops and trades to members (cookies). Build the rest without them.
        log.warning("activity feed unavailable (%s: %s); trades and waivers left out.", type(e).__name__, e)
        activity = []
        client.gaps.append("activity")
    draft = _draft(lg)

    # Transaction counts + FAAB.
    tx = defaultdict(lambda: {"adds": 0, "drops": 0, "faab": 0, "trades": 0})
    for act in activity:
        for tid, kind, _pid, bid in act["moves"]:
            if kind in ("FA ADDED", "WAIVER ADDED"):
                tx[tid]["adds"] += 1
                tx[tid]["faab"] += bid
            elif kind == "DROPPED":
                tx[tid]["drops"] += 1

    # Every player who was drafted, added, dropped or traded needs a name, position and
    # eligibility even if he never showed up in a box score here, and points for any
    # weeks he spent in free agency (the draft, regret and drop features count those).
    moved = {str(pid) for act in activity for _t, kind, pid, _b in act["moves"]
             if pid and kind in ACQUIRED | LET_GO}
    drafted = {p["id"] for p in draft}
    names = {str(bp_id): n for bp_id, n in (getattr(lg, "player_map", {}) or {}).items()
             if isinstance(bp_id, int)}
    names.update({p["id"]: p["name"] for p in draft if p["name"]})
    for w in weeks:
        for r in rosters[w].values():
            names.update({eid: n for eid, (n, _p) in r.players.items()})
    need = {pid for pid in moved | drafted
            if pid not in eligible or any(pid not in pts[w] for w in weeks)}
    try:
        cards = client.player_cards(need) if need else {}
    except Exception as e:  # noqa: BLE001
        log.warning("player card lookup failed (%s); missing weeks count as 0.", e)
        cards = {}
    _backfill(cards, weeks, pts, pos, eligible, pro)
    names.update({pid: c.name for pid, c in cards.items()})
    trades = _parse_trades(activity, lambda pid: names.get(pid, f"Player {pid}"))
    lu = Lineups(pts, eligible, client.slot_counts())

    for i, t in enumerate(trades):
        t["id"] = i + 1
    effs = _effective_weeks(trades, rosters, weeks)
    graded = []
    for i, t in enumerate(trades):
        sides = [_grade_side(i, s, trades, effs, rosters, lu, pos, weeks)
                 for s in t["sides"]]
        for s in sides:
            tx[s["team"]]["trades"] += 1
        graded.append({"id": t["id"], "date": t["date"], "first_week": effs[i],
                       "status": "graded" if effs[i] is not None else "pending",
                       "sides": sides})

    # Weekly team stats: score, best possible lineup (only players who could actually have
    # been started: see _late_adds), all-play.
    late = _late_adds(rosters, reads.kickoff, activity, draft)
    weekly = defaultdict(list)
    for w in weeks:
        scores = {tid: r.score for tid, r in rosters[w].items()}
        for tid, r in rosters[w].items():
            opt = lu.best(set(r.players) - late.get(w, {}).get(tid, set()), w)
            beat = sum(1 for o, s in scores.items() if o != tid and s < r.score)
            tied = sum(1 for o, s in scores.items() if o != tid and s == r.score)
            weekly[tid].append({"week": w, "score": r.score, "optimal": round(max(opt, r.score), 2),
                                "allplay_w": beat, "allplay_l": len(scores) - 1 - beat - tied})

    teams = []
    for t in lg.teams:
        tid = t.team_id
        owner = (t.owners or [{}])[0]
        wk = weekly.get(tid, [])
        scored = sum(x["score"] for x in wk)
        optimal = sum(x["optimal"] for x in wk)
        teams.append({
            "id": tid, "name": (t.team_name or "").strip(), "abbrev": t.team_abbrev,
            "manager": owner.get("firstName") or owner.get("displayName") or "",
            "division": getattr(t, "division_id", None),
            "logo": getattr(t, "logo_url", None),
            "wins": t.wins, "losses": t.losses, "ties": t.ties,
            "points_for": round(t.points_for, 2), "points_against": round(t.points_against, 2),
            "streak": f"{t.streak_type[:1]}{t.streak_length}" if t.streak_length else "",
            "standing": getattr(t, "standing", None),
            "weekly": wk,
            "bench_left": round(optimal - scored, 2),
            "efficiency": round(scored / optimal, 4) if optimal else None,
            "allplay_w": sum(x["allplay_w"] for x in wk),
            "allplay_l": sum(x["allplay_l"] for x in wk),
            **tx[tid],
            "trade_net": _team_trade_net(tid, trades, effs, rosters, lu, weeks),
        })

    settings = lg.settings
    reg_weeks = int(getattr(settings, "reg_season_count", 0) or 0)
    try:
        counters = client.team_counters()
    except Exception as e:  # noqa: BLE001
        log.warning("team counters failed (%s); FAAB remaining falls back to bids.", e)
        counters = {}
    ctx = ReportContext(
        client=client, lg=lg, season=client.season, through=last, current_week=current,
        weeks=weeks, reg_weeks=reg_weeks,
        playoff_teams=int(getattr(settings, "playoff_team_count", 0) or 0),
        rosters=rosters, pts=pts, pos=pos, pro=pro, names=names, lu=lu, matchups=matchups,
        schedule=_schedule(lg, reg_weeks),
        divisions={t.team_id: getattr(t, "division_id", 0) for t in lg.teams},
        division_names=dict(getattr(settings, "division_map", {}) or {}),
        kicks=kicks, activity=activity, trades=graded, teams=teams,
        faab_budget=int(getattr(settings, "acquisition_budget", 0) or 0), counters=counters,
        proj=reads.proj, kickoff=reads.kickoff, late=late, draft=draft)
    ctx.outputs["most_traded"] = _most_traded(trades, pts, pos, pro, weeks)
    return ctx


def build_report(client: EspnClient, through: int | None = None,
                 progress: Callable[[str], None] | None = None) -> dict:
    """``progress(text)``, if given, hears when the ESPN reads are done and the features start."""
    ctx = build_context(client, through)
    if progress:
        progress("Running the numbers…")
    from league import (
        awards,
        clinch,
        draft,
        drops,
        faab,
        history,
        loyalty,
        odds,
        offers,
        power,
        regret,
        streaks,
        style,
        whatif,
        winprob,
    )

    # Features run in this order; each one's output lands in ctx.outputs under its report
    # key, so a later feature can build on an earlier one (style reads faab, offers, loyalty).
    features = [
        ("odds", "odds", odds.build),
        ("power", "power rankings", power.build),
        ("awards", "weekly awards", awards.build),
        ("faab", "FAAB report", faab.build),
        ("offers", "trade offers", offers.build),
        ("history", "league history", history.build),
        ("whatif", "what-if lineups", whatif.build),
        ("regret", "trade regret", regret.build),
        ("streaks", "shame streaks", streaks.build),
        ("draft", "draft report card", draft.build),
        ("drops", "drop regret", drops.build),
        ("loyalty", "player loyalty", loyalty.build),
        ("recap", "win probability recap", winprob.build),
        ("clinch", "clinching scenarios", clinch.build),
        ("style", "manager styles", style.build),
    ]
    for key, name, build in features:
        ctx.outputs[key] = _feature(name, build, ctx)

    out = ctx.outputs
    odds_out = out.pop("odds") or {}
    settings = ctx.lg.settings
    return {
        "punishment": odds_out.get("punishment"),
        "odds_history": odds_out.get("history"),
        "league": {"id": client.league_id, "season": client.season,
                   "name": getattr(settings, "name", "Fantasy League"),
                   "through_week": ctx.through, "current_week": ctx.current_week,
                   "regular_season_weeks": ctx.reg_weeks or None,
                   "playoff_teams": ctx.playoff_teams or None,
                   "faab_budget": ctx.faab_budget or None,
                   "divisions": {str(k): v for k, v in ctx.division_names.items()},
                   "week_kickoffs": {str(w): list(k) for w, k in ctx.kicks.items()},
                   "gaps": list(client.gaps),  # what ESPN wouldn't share without cookies ("activity")
                   "generated_at": datetime.now(UTC).isoformat(timespec="seconds")},
        "teams": ctx.teams,
        "matchups": [{"week": w, "games": ctx.matchups[w]} for w in ctx.weeks],
        "schedule": [{"week": w, "games": [list(g) for g in ctx.schedule[w]]}
                     for w in sorted(ctx.schedule)],
        "trades": ctx.trades,
        **out,
    }
