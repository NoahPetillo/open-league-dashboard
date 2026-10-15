"""Trade offers: how each team answers the offers it gets, and who starts the deals
that go through.

What ESPN lets a league member see decides what's counted here. Every team's
TRADE_DECLINE and TRADE_ACCEPT records are visible (``teamId`` = the team that
answered), so for every team we know how many offers it accepted and declined. A
trade that went through names the team that accepted, so the team on the other side
started it.

Offers sent are only partly visible. Full proposals come back only when they involve
the logged-in team (the "viewer"). For everyone else ESPN still shows a closing
record (a TRADE_PROPOSAL with executionType CANCEL, ``teamId`` = the proposer) for
offers that ended without an answer (withdrawn, expired or replaced), but not for
offers that were declined; ESPN writes the decline and the closing record at the same
moment, and only the decline (by the recipient) is visible. So per team:
    sent = started + unanswered + declined (only those involving the viewer) + pending
is exact for the viewer and a floor (``sent_exact`` False) for everyone else.

``build(ctx)`` returns ``{"teams": [{team, accepted, declined, answered, accept_rate,
started, sent, sent_unanswered, sent_declined, sent_exact}], "accepted", "declined",
"unknown_sender_declines", "viewer", "since"}`` or None if ESPN returned nothing.
"""

from __future__ import annotations

from collections import Counter, defaultdict

MATCH_WINDOW_MS = 24 * 3600 * 1000  # an accept record lands within moments of its trade


def _acceptors(txs: list[dict]) -> list[tuple[int, int]]:
    """``(accepting team, time)`` for every accepted offer. ESPN writes one EXECUTE
    record by the team that accepted (plus a PROCESS record, by the proposer, for
    trades the logged-in team was in)."""
    by_offer: dict[str, list[dict]] = defaultdict(list)
    for t in txs:
        if t.get("type") == "TRADE_ACCEPT" and t.get("relatedTransactionId"):
            by_offer[t["relatedTransactionId"]].append(t)
    out = []
    for recs in by_offer.values():
        ex = next((r for r in recs if r.get("executionType") == "EXECUTE"), None)
        if ex and ex.get("teamId") is not None:
            out.append((int(ex["teamId"]), int(ex.get("proposedDate") or 0)))
    return out


def _starter(acceptor: int, when: int, trades: list[dict], used: set[int]) -> int | None:
    """The team that started an accepted offer: the other side of the matching trade
    (closest in time, accepting team on it, two teams only). None if it can't be told."""
    best = None
    for t in trades:
        teams = {s["team"] for s in t["sides"]}
        if t["id"] in used or acceptor not in teams or len(teams) != 2:
            continue
        gap = abs(int(t.get("date") or 0) - when)
        if gap <= MATCH_WINDOW_MS and (best is None or gap < best[0]):
            best = (gap, t)
    if best is None:
        return None
    used.add(best[1]["id"])
    return next(iter({s["team"] for s in best[1]["sides"]} - {acceptor}))


def _teams_in(t: dict) -> set[int]:
    return {int(x) for i in t.get("items", []) for x in (i.get("fromTeamId"), i.get("toTeamId"))
            if isinstance(x, int) and x > 0}


def _sent(txs: list[dict]) -> tuple[Counter, Counter, Counter, int | None, int]:
    """Offers each team is known to have sent that didn't go through:
    ``(unanswered, declined, pending, viewer, declines with an unknown sender)``."""
    props = [t for t in txs if t.get("type") == "TRADE_PROPOSAL"]
    originals = {t["id"]: t for t in props
                 if t.get("id") and t.get("executionType") != "CANCEL" and t.get("teamId") is not None}
    answered_by: dict[str, str] = {}
    for t in txs:
        if t.get("type") in ("TRADE_DECLINE", "TRADE_ACCEPT") and t.get("relatedTransactionId"):
            answered_by.setdefault(t["relatedTransactionId"], t["type"])
    closed = {t["relatedTransactionId"] for t in props if t.get("executionType") == "CANCEL" and t.get("relatedTransactionId")}
    unanswered, declined, pending = Counter(), Counter(), Counter()
    for t in props:
        if t.get("executionType") == "CANCEL" and t.get("teamId") is not None \
                and t.get("relatedTransactionId") not in answered_by:
            unanswered[int(t["teamId"])] += 1
    for oid, o in originals.items():
        if answered_by.get(oid) == "TRADE_DECLINE":
            declined[int(o["teamId"])] += 1
        elif oid not in answered_by and oid not in closed:
            pending[int(o["teamId"])] += 1
    involved = [_teams_in(o) for o in originals.values() if _teams_in(o)]
    common = set.intersection(*involved) if involved else set()
    viewer = next(iter(common)) if len(common) == 1 else None
    unknown = sum(1 for t in txs if t.get("type") == "TRADE_DECLINE"
                  and t.get("relatedTransactionId") not in originals)
    return unanswered, declined, pending, viewer, unknown


def summarize(txs: list[dict], trades: list[dict], team_ids: list[int]) -> dict | None:
    """Per-team offer answers, offers sent and deals started, from ESPN's raw trade records."""
    if not txs:
        return None
    declined = Counter(int(t["teamId"]) for t in txs
                       if t.get("type") == "TRADE_DECLINE" and t.get("teamId") is not None)
    accepted: Counter = Counter()
    started: Counter = Counter()
    used: set[int] = set()
    for acceptor, when in sorted(_acceptors(txs), key=lambda x: x[1]):
        accepted[acceptor] += 1
        who = _starter(acceptor, when, trades, used)
        if who is not None:
            started[who] += 1
    unanswered, sent_declined, pending, viewer, unknown = _sent(txs)
    rows = []
    for tid in team_ids:
        a, d = accepted[tid], declined[tid]
        rows.append({"team": tid, "accepted": a, "declined": d, "answered": a + d,
                     "accept_rate": round(a / (a + d), 4) if a + d else None,
                     "started": started[tid],
                     "sent": started[tid] + unanswered[tid] + sent_declined[tid] + pending[tid],
                     "sent_unanswered": unanswered[tid], "sent_declined": sent_declined[tid],
                     "sent_exact": tid == viewer})
    dates = [int(t["proposedDate"]) for t in txs if t.get("proposedDate")]
    return {"teams": rows, "accepted": sum(accepted.values()), "declined": sum(declined.values()),
            "unknown_sender_declines": unknown, "viewer": viewer,
            "since": min(dates) if dates else None}


def build(ctx) -> dict | None:
    last = max(ctx.current_week, ctx.through + 1, 1)
    txs = ctx.client.trade_transactions(range(1, last + 1))
    return summarize(txs, ctx.trades, [t["id"] for t in ctx.teams])
