from statistics import mean as _mean, stdev
from typing import Optional

N_TRIALS = 3
KGF_TO_N = 9.80665
ALLOMETRIC_B = 0.67
IMTP_TRIAL_SPREAD_N = 250.0

# Program sheet equation: VO2max (mL/min) = 11.49 x Wpeak + 810
VO2_SLOPE, VO2_INTERCEPT = 11.49, 810.0

# Franchini, Schwartz & Takito (2018), Table 2 - adult male judo athletes.
# Published bands (kgf): Excellent >66 | Good 59-66 (R) / 58-66 (L) |
# Regular 44-58 / 42-57 | Poor 36-43 / 36-41 | Very poor <36.
# Stored as "value must be greater than" cut-offs so decimals from a
# N -> kgf conversion fall into the right band; Poor starts at >= 36.
FRANCHINI_GRIP_KGF = {
    "right": [("Excellent", 66), ("Good", 58), ("Regular", 43), ("Poor", 35.999)],
    "left": [("Excellent", 66), ("Good", 57), ("Regular", 41), ("Poor", 35.999)],
}
FRANCHINI_GRIP_REL = {
    "right": [("Excellent", 0.84), ("Good", 0.75), ("Regular", 0.55), ("Poor", 0.4699)],
    "left": [("Excellent", 0.85), ("Good", 0.73), ("Regular", 0.54), ("Poor", 0.4499)],
}
GRIP_RATING_ORDER = ["Excellent", "Good", "Regular", "Poor", "Very Poor"]

REFERENCES = [
    ("Peak power", "Program's Judo Fitness Test sheet: last watt + (duration / 60) x increment (standard interpolation, Kuipers et al. Int J Sports Med. 1985;6(4):197-201)."),
    ("Predicted VO2max", "Program's Judo Fitness Test sheet: (11.49 x Wpeak + 810) / body mass. Equation origin: Jensen K, Frydkjaer M, Jensen NMB, Bannerholt LM, Gam S. A maximal rowing ergometer protocol to predict maximal oxygen uptake. Int J Sports Physiol Perform. 2021;16(3):382-386. doi:10.1123/ijspp.2019-0932"),
    ("IMTP method + 250 N rule", "Comfort P, Dos'Santos T, Beckham GK, Stone MH, Guppy SN, Haff GG. Standardization and methodological considerations for the isometric midthigh pull. Strength Cond J. 2019;41(2):57-79."),
    ("Allometric scaling 0.67", "Jaric S. Muscle strength testing: use of normalisation for body size. Sports Med. 2002;32(10):615-631; Folland JP, et al. Eur J Appl Physiol. 2008;102:739-745."),
    ("Handgrip scaling in judo", "Kulkamp W, Ache-Dias J, Kons RL, Detanico D, Dal Pupo J. The ratio standard is not adequate for scaling handgrip strength in judo athletes and nonathletes. J Exerc Rehabil. 2020;16(2):175-182."),
    ("Handgrip norms (judo)", "Franchini E, Schwartz J, Takito MY. Maximal isometric handgrip strength: comparison between weight categories and classificatory table for adult judo athletes. J Exerc Rehabil. 2018;14(6):968-973."),
    ("Handgrip protocol", "Roberts HC, et al. A review of the measurement of grip strength in clinical and epidemiological studies: towards a standardised approach. Age Ageing. 2011;40(4):423-429."),
    ("Asymmetry", "Bishop C, Read P, Chavda S, Turner A. Asymmetries of the lower limb: the calculation conundrum in strength training and conditioning. Strength Cond J. 2016;38(6):27-32; Bishop C, et al. Interlimb asymmetries: understanding how to calculate differences from bilateral and unilateral tests. Strength Cond J. 2018;40(4):1-6."),
]


def _vals(values):
    return [float(v) for v in values if v is not None]


def best(values) -> Optional[float]:
    v = _vals(values)
    return max(v) if v else None


def likely_typo(value, others) -> bool:
    """Data-entry check: a trial under half of the same measure's other
    trials is almost always a typing slip (e.g. 69 for 690)."""
    others = _vals(others)
    return bool(others) and value is not None and float(value) < 0.5 * min(others)


def clean_trials(values):
    """Trials with likely typos removed - used only for the noise (CV)
    estimate, never to change the recorded best."""
    v = _vals(values)
    return [x for i, x in enumerate(v) if not likely_typo(x, v[:i] + v[i + 1:])]


def trial_cv(values) -> Optional[float]:
    """Within-session coefficient of variation (%) across trials."""
    v = clean_trials(values)
    if len(v) < 2 or _mean(v) == 0:
        return None
    return round(stdev(v) / _mean(v) * 100, 1)


def compute_peak_power(last_watt, duration_s, increment) -> Optional[float]:
    """Peak power (W), exactly as the program's sheet: last watt + (duration / 60) x increment."""
    if last_watt is None:
        return None
    return round(float(last_watt) + (float(duration_s or 0) / 60.0) * float(increment or 0), 2)


def compute_vo2max(peak_power, body_mass) -> Optional[float]:
    """Predicted VO2max (mL/kg/min), exactly as the program's sheet."""
    if peak_power is None or not body_mass:
        return None
    return round((VO2_SLOPE * float(peak_power) + VO2_INTERCEPT) / float(body_mass), 1)


def ratio_scaled(value, body_mass) -> Optional[float]:
    if value is None or not body_mass:
        return None
    return round(float(value) / float(body_mass), 2)


def allometric(value, body_mass, b=ALLOMETRIC_B) -> Optional[float]:
    if value is None or not body_mass:
        return None
    return round(float(value) / (float(body_mass) ** b), 1)


def asymmetry(right, left) -> Optional[float]:
    """Bishop et al. (2018) percentage difference for unilateral tests."""
    if right is None or left is None or max(right, left) == 0:
        return None
    return round((max(right, left) - min(right, left)) / max(right, left) * 100, 1)


def stronger_side(right, left) -> Optional[str]:
    if right is None or left is None or right == left:
        return None
    return "Right" if right > left else "Left"


def grip_rating(value, side, relative=False) -> Optional[str]:
    """Franchini et al. (2018) band for adult male judo athletes."""
    if value is None:
        return None
    table = FRANCHINI_GRIP_REL if relative else FRANCHINI_GRIP_KGF
    for label, cutoff in table[side]:
        if value > cutoff:
            return label
    return "Very Poor"


def summarize(test: dict, gender: Optional[str] = None) -> dict:
    """Derived metrics for one judo_tests row with its 'trials' list attached."""
    trials = sorted(test.get("trials") or [], key=lambda t: t["trial_no"])
    mass = test.get("body_mass")
    gender = gender or (test.get("athletes") or {}).get("gender")

    def col(name):
        return [t.get(name) for t in trials]

    grip_r, grip_l = best(col("grip_right")), best(col("grip_left"))
    rfd_r, rfd_l = best(col("max_rfd_right")), best(col("max_rfd_left"))
    imtp_best = best(col("imtp_peak"))
    peak_power = compute_peak_power(test.get("ramp_last_watt"), test.get("ramp_duration_s"), test.get("ramp_increment"))

    grip_cv = [c for c in (trial_cv(col("grip_right")), trial_cv(col("grip_left"))) if c is not None]
    rfd_cv = [c for c in (trial_cv(col("max_rfd_right")), trial_cv(col("max_rfd_left"))) if c is not None]
    grip_asym, rfd_asym = asymmetry(grip_r, grip_l), asymmetry(rfd_r, rfd_l)
    grip_noise = round(_mean(grip_cv), 1) if grip_cv else None
    rfd_noise = round(_mean(rfd_cv), 1) if rfd_cv else None

    imtp_vals = _vals(col("imtp_peak"))
    grip_best = best([grip_r, grip_l])

    is_male = gender == "Male"
    kgf = lambda n: n / KGF_TO_N if n is not None else None  # noqa: E731

    return {
        "gender": gender,
        "body_mass": mass,
        # handgrip
        "grip_best_right": grip_r, "grip_best_left": grip_l,
        "grip_best_right_kgf": round(kgf(grip_r), 1) if grip_r is not None else None,
        "grip_best_left_kgf": round(kgf(grip_l), 1) if grip_l is not None else None,
        "grip_allo": allometric(grip_best, mass),
        "grip_rating_right": grip_rating(kgf(grip_r), "right") if is_male else None,
        "grip_rating_left": grip_rating(kgf(grip_l), "left") if is_male else None,
        "grip_asym": grip_asym, "grip_cv": grip_noise,
        "grip_asym_flag": (grip_asym is not None and grip_noise is not None and grip_asym > grip_noise),
        "rfd_best_right": rfd_r, "rfd_best_left": rfd_l,
        "rfd_asym": rfd_asym, "rfd_cv": rfd_noise,
        "rfd_asym_flag": (rfd_asym is not None and rfd_noise is not None and rfd_asym > rfd_noise),
        # IMTP
        "imtp_trials": col("imtp_peak"),
        "imtp_best": imtp_best,
        "imtp_rel": ratio_scaled(imtp_best, mass),
        "imtp_rel_trials": [ratio_scaled(v, mass) for v in col("imtp_peak")],
        "imtp_allo": allometric(imtp_best, mass),
        "imtp_spread": (max(imtp_vals) - min(imtp_vals)) if len(imtp_vals) > 1 else None,
        # ramp
        "peak_power": peak_power,
        "power_per_kg": ratio_scaled(peak_power, mass),
        "vo2max": compute_vo2max(peak_power, mass),
        "peak_hr": test.get("ramp_peak_hr"),
    }


def entry_checks(trials: list, ramp_duration_s=None, ramp_last_watt=None) -> list:
    """Entry-time checks. Protocol rules cite their source; plain data-entry
    sanity checks are labelled as such."""
    warnings = []

    imtp = _vals([t.get("imtp_peak") for t in trials])
    if len(imtp) > 1 and max(imtp) - min(imtp) > IMTP_TRIAL_SPREAD_N:
        warnings.append(f"IMTP trials differ by {max(imtp) - min(imtp):.0f} N. Comfort et al. (2019) recommend further trials "
                        f"until peak forces are within {IMTP_TRIAL_SPREAD_N:.0f} N.")
    elif len(imtp) == 1:
        warnings.append("Only one IMTP trial entered. Comfort et al. (2019) recommend at least two valid trials.")

    for t in trials:
        for side in ("right", "left"):
            mx, av = t.get(f"max_rfd_{side}"), t.get(f"avg_rfd_{side}")
            if mx is not None and av is not None and av > mx:
                warnings.append(f"Trial {t['trial_no']} {side.title()}: Average RFD ({av:g}) is higher than Max RFD ({mx:g}). "
                                f"An average can't exceed its maximum - values may be swapped.")

    # Data-entry sanity check (not a published criterion): a grip trial below
    # half of the same hand's other trials is almost always a typo.
    for key, label in (("grip_right", "Right"), ("grip_left", "Left")):
        vals = [(t["trial_no"], t.get(key)) for t in trials if t.get(key) is not None]
        for trial_no, v in vals:
            if likely_typo(v, [o for n, o in vals if n != trial_no]):
                warnings.append(f"Handgrip {label}, Trial {trial_no}: {v:g} N is under half of this hand's other trials - likely a typo (data-entry check).")

    if ramp_last_watt is not None and ramp_duration_s == 0:
        warnings.append("Ramp test: 0 s completed in the final step. Confirm this isn't a missing value - it lowers peak power and predicted VO2max.")
    return warnings
