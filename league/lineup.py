"""Best possible starting lineup for a set of players, given their points.

Eligibility comes straight from ESPN (each player's ``eligibleSlots``), so any
league format works — FLEX, superflex, IDP, head coach — with no position tables.
"""

from __future__ import annotations


def best_lineup(points: dict[str, float], eligible: dict[str, list[str]],
                player_ids, slot_counts: dict[str, int]) -> tuple[float, set[str]]:
    """Greedy best legal lineup → (total points, starters).

    Slots are filled most-restrictive first (fewest eligible players), each taking
    the highest scorer still available. For nested flex rules (RB ⊂ FLEX ⊂ OP)
    that is optimal: dedicated slots claim their best players before a FLEX
    competes for the leftovers.
    """
    ids = list(player_ids)
    pool = {s: [i for i in ids if s in (eligible.get(i) or ())] for s in slot_counts}
    used: set[str] = set()
    total = 0.0
    for slot in sorted(slot_counts, key=lambda s: len(pool[s])):
        candidates = sorted((i for i in pool[slot] if i not in used),
                            key=lambda i: points.get(i, 0.0), reverse=True)
        for pid in candidates[: slot_counts[slot]]:
            used.add(pid)
            total += points.get(pid, 0.0)
    return round(total, 2), used
