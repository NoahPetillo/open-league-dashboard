"""Trade offers: answers per team (accepted / declined) and who started each deal."""

from __future__ import annotations

from league.offers import summarize

H = 3600 * 1000


def _trade(tid, date, a, b):
    return {"id": tid, "date": date, "sides": [{"team": a}, {"team": b}]}


def _accept(offer, team, when, kind="EXECUTE"):
    return {"type": "TRADE_ACCEPT", "relatedTransactionId": offer, "teamId": team,
            "executionType": kind, "proposedDate": when}


def _decline(team, when=0):
    return {"type": "TRADE_DECLINE", "teamId": team, "relatedTransactionId": f"x{when}",
            "executionType": "EXECUTE", "proposedDate": when}


def test_answers_and_starters():
    trades = [_trade(1, 100 * H, 1, 2), _trade(2, 200 * H, 3, 1)]
    txs = [
        _accept("o1", 2, 100 * H - 5000),            # 2 accepted 1's offer → 1 started trade 1
        _accept("o1", 1, 100 * H - 4000, "PROCESS"),  # the proposer's processing record: not an answer
        _accept("o2", 1, 200 * H - 1000),            # 1 accepted 3's offer → 3 started trade 2
        _decline(1, 50 * H), _decline(1, 60 * H), _decline(3, 70 * H),
        {"type": "TRADE_PROPOSAL", "teamId": 1, "proposedDate": 10 * H, "items": []},
    ]
    out = summarize(txs, trades, [1, 2, 3, 4])
    rows = {r["team"]: r for r in out["teams"]}
    assert (rows[1]["accepted"], rows[1]["declined"], rows[1]["answered"]) == (1, 2, 3)
    assert rows[1]["accept_rate"] == round(1 / 3, 4)
    assert (rows[2]["accepted"], rows[2]["declined"], rows[2]["accept_rate"]) == (1, 0, 1)
    assert rows[4]["answered"] == 0 and rows[4]["accept_rate"] is None
    assert (rows[1]["started"], rows[3]["started"], rows[2]["started"]) == (1, 1, 0)
    assert (out["accepted"], out["declined"], out["since"]) == (2, 3, 10 * H)


def _offer(oid, proposer, other, when=0):
    return {"type": "TRADE_PROPOSAL", "id": oid, "teamId": proposer, "executionType": "EXECUTE",
            "proposedDate": when, "items": [{"fromTeamId": proposer, "toTeamId": other},
                                            {"fromTeamId": other, "toTeamId": proposer}]}


def _closed(oid, proposer, other, when=0):
    return {**_offer(f"c-{oid}", proposer, other, when), "executionType": "CANCEL",
            "relatedTransactionId": oid}


def test_offers_sent_exact_for_the_viewer_and_a_floor_for_everyone_else():
    # Team 5 is the logged-in team: its offers come back in full. Team 9's offer to team 2
    # isn't visible, only its closing record (withdrawn); team 2's decline of a hidden offer
    # has an unknown sender.
    trades = [_trade(1, 100 * H, 5, 4)]
    txs = [
        _offer("a", 5, 4, 99 * H), _accept("a", 4, 100 * H),                       # 5 started a trade
        _offer("b", 5, 9, 10 * H), _closed("b", 5, 9, 11 * H),
        {**_decline(9, 11 * H), "relatedTransactionId": "b"},                     # 5's offer, declined
        _offer("c", 9, 5, 20 * H), _closed("c", 9, 5, 30 * H),                     # 9's offer, withdrawn
        _offer("d", 5, 1, 40 * H),                                                 # 5's offer, still open
        _closed("hidden", 9, 2, 50 * H),                                           # 9 → 2, withdrawn
        {**_decline(2, 60 * H), "relatedTransactionId": "secret"},                # sender unknown
    ]
    out = summarize(txs, trades, [1, 2, 4, 5, 9])
    rows = {r["team"]: r for r in out["teams"]}
    assert out["viewer"] == 5 and out["unknown_sender_declines"] == 1
    assert (rows[5]["sent"], rows[5]["started"], rows[5]["sent_declined"], rows[5]["sent_exact"]) == (3, 1, 1, True)
    assert (rows[9]["sent"], rows[9]["sent_unanswered"], rows[9]["sent_exact"]) == (2, 2, False)
    assert rows[2]["sent"] == 0 and rows[2]["declined"] == 1


def test_an_accept_far_from_any_trade_starts_nothing():
    out = summarize([_accept("o1", 2, 0)], [_trade(1, 30 * 24 * H, 1, 2)], [1, 2])
    rows = {r["team"]: r for r in out["teams"]}
    assert rows[2]["accepted"] == 1 and rows[1]["started"] == 0


def test_two_accepts_never_claim_the_same_trade():
    trades = [_trade(1, 100 * H, 1, 2)]
    out = summarize([_accept("a", 2, 100 * H), _accept("b", 2, 100 * H + 1)], trades, [1, 2])
    assert {r["team"]: r["started"] for r in out["teams"]}[1] == 1


def test_nothing_from_espn_means_no_section():
    assert summarize([], [], [1, 2]) is None
