from typing import List, Optional


def compute_peak_time(set_totals: List[float]) -> Optional[float]:
    return min(set_totals) if set_totals else None


def compute_duration(set_totals: List[float]) -> Optional[float]:
    return sum(set_totals) if set_totals else None


def compute_fatigue_index(set_totals: List[float]) -> Optional[float]:
    """Standard RSA fatigue decrement: how much slower the actual total was
    vs. an 'ideal' total (best set repeated N times), as a percentage."""
    if not set_totals:
        return None
    peak = min(set_totals)
    actual_total = sum(set_totals)
    ideal_total = peak * len(set_totals)
    if ideal_total == 0:
        return None
    return round((actual_total - ideal_total) / ideal_total * 100, 1)


PEAK_TIME_BANDS = {
    "Male": {"good": 21.0, "avg": 24.0},
    "Female": {"good": 23.5, "avg": 26.5},
}
FATIGUE_INDEX_BANDS = {"good": 4.5, "avg": 8.0}


def rate_peak_time(peak: Optional[float], gender: Optional[str]) -> Optional[str]:
    if peak is None or gender not in PEAK_TIME_BANDS:
        return None
    bands = PEAK_TIME_BANDS[gender]
    if peak < bands["good"]:
        return "Good"
    if peak < bands["avg"]:
        return "Average"
    return "Bad"


def rate_fatigue_index(fatigue: Optional[float]) -> Optional[str]:
    if fatigue is None:
        return None
    if fatigue < FATIGUE_INDEX_BANDS["good"]:
        return "Good"
    if fatigue < FATIGUE_INDEX_BANDS["avg"]:
        return "Average"
    return "Bad"
