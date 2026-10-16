from typing import Optional


def compute_split_velocity(distance_m: float, time_s: float) -> Optional[float]:
    if not time_s or time_s <= 0:
        return None
    return round(distance_m / time_s, 2)


def compute_attempt_velocities(first_10m: float, split_10_15: float, split_15_20: float) -> dict:
    """Average velocity (m/s) for each segment of the approach run."""
    return {
        "v_0_10": compute_split_velocity(10, first_10m),
        "v_10_15": compute_split_velocity(5, split_10_15),
        "v_15_20": compute_split_velocity(5, split_15_20),
    }


def compute_total_time(first_10m: float, split_10_15: float, split_15_20: float) -> float:
    return round((first_10m or 0) + (split_10_15 or 0) + (split_15_20 or 0), 3)


def is_still_accelerating(v_10_15: Optional[float], v_15_20: Optional[float]) -> Optional[bool]:
    """Whether velocity is still rising into the final segment (typical for
    developing athletes, who haven't yet reached max velocity by 20m) versus
    having plateaued or dropped (approaching/at max velocity already)."""
    if v_10_15 is None or v_15_20 is None:
        return None
    return v_15_20 > v_10_15
