from typing import List, Optional, Tuple


def compute_set_result(player_score: Optional[int], opponent_score: Optional[int]) -> Optional[str]:
    """Return 'Win' / 'Lose' / 'Draw' / None (if scores not yet entered)."""
    if player_score is None or opponent_score is None:
        return None
    if player_score > opponent_score:
        return "Win"
    if player_score < opponent_score:
        return "Lose"
    return "Draw"  # not expected in squash, but don't silently misclassify


def majority_needed(max_sets: int) -> int:
    return max_sets // 2 + 1


def compute_match_result(set_results: List[Optional[str]], max_sets: int) -> Tuple[str, str]:
    """
    set_results: ordered list of 'Win'/'Lose'/'Draw'/None for each set entered so far.
    Returns (match_result, score_summary) e.g. ("Win", "3-1") or ("Incomplete", "2-2").
    """
    played = [r for r in set_results if r in ("Win", "Lose")]
    wins = played.count("Win")
    losses = played.count("Lose")
    majority = majority_needed(max_sets)

    if wins >= majority:
        return "Win", f"{wins}-{losses}"
    if losses >= majority:
        return "Lose", f"{wins}-{losses}"

    # Can't reach majority at all even if all remaining sets go one way?
    # (Not strictly necessary for squash's 5-set case, but keeps this robust
    # if a future sport has a larger max_sets.)
    return "Incomplete", f"{wins}-{losses}"


def sets_remaining_possible(num_played: int, max_sets: int) -> int:
    """How many more sets could still be played in this match."""
    return max(0, max_sets - num_played)
