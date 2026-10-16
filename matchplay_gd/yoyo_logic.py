from typing import Optional

# Cumulative distance (m) completed at the END of each level.
# Levels 6-8 don't exist in the real IR1 protocol - the test skips from
# level 5 straight to level 9.
_CUMULATIVE_DISTANCE_AT_END_OF_LEVEL = {
    5: 40, 9: 80, 11: 160, 12: 280, 13: 440, 14: 760, 15: 1080,
    16: 1400, 17: 1720, 18: 2040, 19: 2360, 20: 2680, 21: 3000,
    22: 3320, 23: 3640,
}
_LEVELS_SORTED = sorted(_CUMULATIVE_DISTANCE_AT_END_OF_LEVEL)


def compute_distance(level: int, shuttle: int) -> Optional[float]:
    """Total distance (m) covered, given the level and shuttle number reached."""
    prior_levels = [l for l in _LEVELS_SORTED if l < level]
    dist_before_level = _CUMULATIVE_DISTANCE_AT_END_OF_LEVEL[prior_levels[-1]] if prior_levels else 0
    return dist_before_level + shuttle * 40


def compute_vo2max(distance_m: float) -> float:
    """Bangsbo et al. 2008 formula."""
    return round(distance_m * 0.0084 + 36.4, 1)


# Normative bands from this program's own Yo-Yo test sheet (Level.Shuttle score)
_BANDS = {
    "Male": [
        ("Elite", 20.1, None),
        ("Excellent", 18.7, 20.1),
        ("Good", 17.3, 18.6),
        ("Average", 15.7, 17.2),
        ("Below Average", 14.2, 15.6),
        ("Very Poor", None, 14.2),
    ],
    "Female": [
        ("Elite", 17.5, None),
        ("Excellent", 16.6, 17.5),
        ("Good", 15.6, 16.5),
        ("Average", 14.6, 15.5),
        ("Below Average", 13.1, 14.5),
        ("Very Poor", None, 13.1),
    ],
}


def compute_score(level: int, shuttle: int) -> float:
    """The 'Level.Shuttle' score as commonly reported, e.g. 20.2."""
    return round(level + shuttle / 10, 1)


def rate_score(score: float, gender: Optional[str]) -> Optional[str]:
    if gender not in _BANDS:
        return None
    for label, low, high in _BANDS[gender]:
        if low is not None and score < low:
            continue
        if high is not None and score >= high:
            continue
        return label
    return None


def next_tier_target(score: float, gender: Optional[str]):
    """Returns (next_tier_label, score_needed) for the tier just above the
    athlete's current one, or None if gender is unknown or already Elite."""
    if gender not in _BANDS:
        return None
    bands = _BANDS[gender]  # ordered best (Elite) to worst (Very Poor)
    current_idx = None
    for i, (label, low, high) in enumerate(bands):
        if (low is None or score >= low) and (high is None or score < high):
            current_idx = i
            break
    if current_idx is None or current_idx == 0:
        return None
    next_label, next_low, _ = bands[current_idx - 1]
    return next_label, next_low


def next_tier_target_real(level: int, shuttle: int, gender: Optional[str]):
    """Like next_tier_target, but the gap is computed in real shuttles/meters
    via the actual distance table - not decimal subtraction on the
    Level.Shuttle score, which is misleading once a level has more than
    9 shuttles (e.g. 14.8 -> 15.6 is NOT "0.8 more"; levels 14+ have 16
    shuttles per level, so the real gap has to come from distance)."""
    score = compute_score(level, shuttle)
    target = next_tier_target(score, gender)
    if not target:
        return None
    next_label, next_low = target
    # Band threshold values in _BANDS are always single-digit-shuttle
    # notation (verified against the reference table), so this parse is
    # safe - unlike scanning forward with compute_score(), which can drift
    # into double-digit shuttle numbers that collide with the next level.
    next_level = int(next_low)
    next_shuttle = round((next_low - next_level) * 10)
    current_dist = compute_distance(level, shuttle)
    target_dist = compute_distance(next_level, next_shuttle)
    meters_needed = target_dist - current_dist
    shuttles_needed = round(meters_needed / 40)
    return {
        "next_label": next_label, "next_level": next_level, "next_shuttle": next_shuttle,
        "meters_needed": meters_needed, "shuttles_needed": shuttles_needed,
    }


def estimate_hr_max(age: Optional[int]) -> Optional[int]:
    """Tanaka, Monahan & Seals (2001) formula - better-validated than the
    older 220-age rule of thumb."""
    if not age:
        return None
    return round(208 - 0.7 * age)


def lactate_clearance_rate(peak_value: float, peak_minute: float, last_value: float, last_minute: float) -> Optional[float]:
    """mmol/L cleared per minute, from peak to the last recorded sample."""
    if peak_value is None or last_value is None or last_minute is None or last_minute <= peak_minute:
        return None
    return round((peak_value - last_value) / (last_minute - peak_minute), 2)
