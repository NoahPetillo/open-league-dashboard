"""Read-only ESPN access — a thin wrapper over the ``espn-api`` package.

ESPN has no write API; everything here only reads. A private league needs the
``espn_s2`` and ``SWID`` cookies from a logged-in browser session.
"""

from __future__ import annotations

import json

# ESPN activity message types (same mapping espn-api uses), plus 290: FAAB dollars
# that moved in an accepted trade (284/286 are FAAB in proposals/declined offers).
_MESSAGE_TYPES = {178: "FA ADDED", 180: "WAIVER ADDED", 179: "DROPPED", 181: "DROPPED",
                  239: "DROPPED", 244: "TRADE", 290: "TRADE FAAB"}


def braced(swid: str | None) -> str | None:
    """SWID wrapped in braces, which ESPN expects (people often copy it without)."""
    s = (swid or "").strip()
    if not s:
        return None
    return ("" if s.startswith("{") else "{") + s + ("" if s.endswith("}") else "}")


class EspnClient:
    def __init__(self, league_id: int, season: int, espn_s2: str | None = None, swid: str | None = None):
        if not league_id:
            raise ValueError("No ESPN league given.")
        self.league_id = int(league_id)
        self.season = int(season)
        self.espn_s2 = (espn_s2 or "").strip() or None
        self.swid = braced(swid)
        self.gaps: list[str] = []  # parts of the league ESPN wouldn't share (see report.build_context)
        self._league = None

    def league(self):
        """The espn-api ``League`` (fetched once, then cached on this client)."""
        if self._league is None:
            from espn_api.football import League

            self._league = League(league_id=self.league_id, year=self.season,
                                  espn_s2=self.espn_s2, swid=self.swid)
        return self._league

    def teams(self):
        return self.league().teams

    def box_scores(self, week: int | None = None):
        return self.league().box_scores(week)

    def recent_activity(self, size: int = 25, offset: int = 0):
        return self.league().recent_activity(size=size, offset=offset)

    def transactions(self, page: int = 100) -> list[dict]:
        """Every add, drop and trade this season, oldest first, as plain records:
        ``{"date": ms, "moves": [(team_id, action, player_id, faab_bid), ...]}``.
        FAAB traded in a deal comes through as ``FAAB_SENT``/``FAAB_RECEIVED`` rows
        (player id ``""``, the dollars in the last field) alongside the trade's players.

        Same ESPN endpoint as espn-api's ``recent_activity``, but that wraps each
        move in a full Player object fetched one HTTP request at a time (~1 min per
        100 moves). Callers resolve player names/positions in one batch instead.
        """
        lg = self.league()
        out, offset = [], 0
        while True:
            filters = {"topics": {
                "filterType": {"value": ["ACTIVITY_TRANSACTIONS"]},
                "limit": page, "limitPerMessageSet": {"value": 25}, "offset": offset,
                "sortMessageDate": {"sortPriority": 1, "sortAsc": False},
                "sortFor": {"sortPriority": 2, "sortAsc": False},
                "filterIncludeMessageTypeIds": {"value": list(_MESSAGE_TYPES)},
            }}
            data = lg.espn_request.league_get(
                extend="/communication/", params={"view": "kona_league_communication"},
                headers={"x-fantasy-filter": json.dumps(filters)})
            topics = data.get("topics", [])
            for topic in topics:
                moves = []
                for msg in topic.get("messages", []):
                    kind = _MESSAGE_TYPES.get(msg.get("messageTypeId"))
                    pid = str(msg.get("targetId"))
                    if kind == "TRADE":
                        moves.append((msg.get("from"), "TRADE_SENT", pid, 0))
                        moves.append((msg.get("to"), "TRADE_RECEIVED", pid, 0))
                    elif kind == "TRADE FAAB":  # targetId is the dollar amount
                        amount = int(msg.get("targetId") or 0)
                        moves.append((msg.get("from"), "FAAB_SENT", "", amount))
                        moves.append((msg.get("to"), "FAAB_RECEIVED", "", amount))
                    elif kind == "WAIVER ADDED":
                        moves.append((msg.get("to"), kind, pid, int(msg.get("from") or 0)))
                    elif kind:
                        moves.append((msg.get("for") if msg.get("messageTypeId") == 239
                                      else msg.get("to"), kind, pid, 0))
                out.append({"date": int(topic.get("date", 0)), "moves": moves})
            if len(topics) < page:
                return sorted(out, key=lambda t: t["date"])
            offset += page

    def player_cards(self, player_ids) -> dict[str, object]:
        """espn-api Player cards (name, position, eligibleSlots, weekly stats), batched."""
        ids = sorted({int(p) for p in player_ids})
        cards = {}
        for i in range(0, len(ids), 50):
            got = self.league().player_info(playerId=ids[i:i + 50]) or []
            for card in got if isinstance(got, list) else [got]:
                cards[str(card.playerId)] = card
        return cards

    def trade_transactions(self, weeks) -> list[dict]:
        """ESPN's raw trade records (TRADE_PROPOSAL / _ACCEPT / _DECLINE / _UPHOLD …) for
        the given scoring periods, de-duplicated. The preseason is period 1. ESPN shows
        every team's accept/decline records, but full proposals only when they involve
        the logged-in team."""
        out: dict[str, dict] = {}
        for sp in weeks:
            raw = self.league().espn_request.league_get(
                params={"view": "mTransactions2", "scoringPeriodId": sp})
            for tx in raw.get("transactions", []):
                if "TRADE" in tx.get("type", "") and tx.get("id"):
                    out.setdefault(tx["id"], tx)
        return list(out.values())

    def team_counters(self) -> dict[int, dict]:
        """ESPN's own per-team transaction counters (acquisitionBudgetSpent, trades, …)."""
        raw = self.league().espn_request.league_get(params={"view": "mTeam"})
        return {int(t["id"]): t.get("transactionCounter", {}) for t in raw.get("teams", [])}

    def slot_counts(self) -> dict[str, int]:
        """Starting lineup slots → how many of each (bench/IR excluded)."""
        counts = getattr(self.league().settings, "position_slot_counts", {}) or {}
        return {s: int(n) for s, n in counts.items() if n and s not in ("BE", "IR", "")}
