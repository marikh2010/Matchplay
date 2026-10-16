import datetime
import streamlit as st
import db
from match_logic import compute_set_result, compute_match_result, majority_needed
from yoyo_logic import compute_score, compute_distance, compute_vo2max, rate_score
from longjump_logic import compute_attempt_velocities, compute_total_time
from judo_logic import (
    N_TRIALS, summarize as judo_summarize, entry_checks as judo_entry_checks,
)
from style import apply_style


def render(sport):
    apply_style(sport["name"])
    st.title(f"\U0001F4DD {sport['name']} entry")

    entry_types = db.list_entry_types(sport["id"])
    if not entry_types:
        st.warning(f"No entry types set up for {sport['name']} yet.")
        st.stop()

    if len(entry_types) > 1:
        et_name = st.selectbox("Entry Type", [et["name"] for et in entry_types])
        entry_type = next(et for et in entry_types if et["name"] == et_name)
    else:
        entry_type = entry_types[0]

    st.divider()

    name = entry_type["name"]
    if name == "Match Play":
        _render_matchplay(sport, entry_type)
    elif name == "RSA Test":
        _render_rsa(sport, entry_type)
    elif name == "Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test":
        _render_yoyo(sport, entry_type)
    elif name == "Long Jump Test":
        _render_longjump(sport, entry_type)
    elif name == "Judo Fitness Test":
        _render_judo(sport, entry_type)
    else:
        st.error(f"No entry form built for '{name}' yet.")


def _athlete_picker(sport):
    athletes = db.list_athletes(sport_id=sport["id"])
    if not athletes:
        st.warning(f"No athletes added for {sport['name']} yet. Go to Admin and add one first.")
        st.stop()
    lookup = {a["name"]: a for a in athletes}
    return lookup[st.selectbox("Athlete", list(lookup.keys()))]


# =====================================================================
# Match Play
# =====================================================================
def _render_matchplay(sport, entry_type):
    athlete = _athlete_picker(sport)
    st.divider()

    col1, col2 = st.columns(2, gap="large")
    with col1:
        match_date = st.date_input("Date", value=datetime.date.today())
    with col2:
        category = st.selectbox("Category", ["Training", "Tournament"])

    stages = db.list_stages(entry_type["id"])
    if category == "Tournament" and stages:
        stage = st.selectbox("Stage", [s["name"] for s in stages])
    else:
        stage = "Training"

    known_opponents = db.list_known_opponents()
    opponent_choice = st.selectbox("Opponent", options=["\u2795 New opponent..."] + known_opponents)
    opponent_name = st.text_input("Opponent name") if opponent_choice == "\u2795 New opponent..." else opponent_choice

    max_sets = st.selectbox("Match format", options=[3, 5], index=1,
                             help="Best of 3 = win at 2 sets. Best of 5 = win at 3 sets.")

    suggested_no = db.next_match_no(athlete["id"], category)
    match_no = st.number_input("Match No.", min_value=1, value=suggested_no, step=1)

    st.divider()
    st.subheader(f"Sets (up to {max_sets})")
    if "mp_num_sets" not in st.session_state:
        st.session_state.mp_num_sets = 1

    set_rows = []
    for i in range(st.session_state.mp_num_sets):
        with st.expander(f"Set {i + 1}", expanded=(i == st.session_state.mp_num_sets - 1)):
            c1, c2 = st.columns(2, gap="large")
            with c1:
                ps = st.number_input("Player score", min_value=0, max_value=99, key=f"mp_ps_{i}")
            with c2:
                os_ = st.number_input("Opponent score", min_value=0, max_value=99, key=f"mp_os_{i}")
            result = compute_set_result(ps, os_)
            if result:
                st.caption(f"Set result: **{result}**")

            c1, c2, c3 = st.columns(3, gap="large")
            with c1:
                rpe = st.number_input("RPE (0-10)", min_value=0, max_value=10, value=5, key=f"mp_rpe_{i}")
                t = st.time_input("Duration (HH:MM:SS)", value=None, step=1, key=f"mp_dur_{i}")
                duration = None if t is None else t.hour * 3600 + t.minute * 60 + t.second
            with c2:
                avg_hr = st.number_input("Avg HR", min_value=0, value=None, placeholder="Not entered", key=f"mp_avghr_{i}")
                avg_hr_pct = st.number_input("Avg HR (%HRmax)", min_value=0, max_value=100, value=None, placeholder="Not entered", key=f"mp_avghrpct_{i}")
                peak_hr = st.number_input("Peak HR", min_value=0, value=None, placeholder="Not entered", key=f"mp_peakhr_{i}")
                end_hr = st.number_input("End HR", min_value=0, value=None, placeholder="Not entered", key=f"mp_endhr_{i}")
                hr_recovery = st.number_input("1-min HR Recovery", min_value=0, value=None, placeholder="Not entered", key=f"mp_hrrec_{i}")
            with c3:
                cardio_load = st.number_input("Cardio Load", min_value=0.0, value=None, placeholder="Not entered", key=f"mp_load_{i}")
                resting_lactate = st.number_input("Resting Lactate", min_value=0.0, value=None, placeholder="Not entered", key=f"mp_rlac_{i}")
                lactate = st.number_input("Lactate", min_value=0.0, value=None, placeholder="Not entered", key=f"mp_lac_{i}")
                resting_glucose = st.number_input("Resting Glucose", min_value=0.0, value=None, placeholder="Not entered", key=f"mp_rgluc_{i}")
                glucose = st.number_input("Glucose", min_value=0.0, value=None, placeholder="Not entered", key=f"mp_gluc_{i}")

            set_rows.append({
                "set_no": i + 1, "player_score": int(ps), "opponent_score": int(os_), "rpe": int(rpe),
                "duration_seconds": duration, "avg_hr": avg_hr, "avg_hr_pct": avg_hr_pct, "peak_hr": peak_hr, "end_hr": end_hr,
                "hr_recovery": hr_recovery, "cardio_load": cardio_load, "resting_lactate": resting_lactate,
                "lactate": lactate, "resting_glucose": resting_glucose, "glucose": glucose,
            })

    col1, col2 = st.columns(2, gap="large")
    with col1:
        if st.session_state.mp_num_sets < max_sets:
            if st.button("\u2795 Add another set"):
                st.session_state.mp_num_sets += 1
                st.rerun()
    with col2:
        if st.session_state.mp_num_sets > 1:
            if st.button("\u2796 Remove last set"):
                st.session_state.mp_num_sets -= 1
                st.rerun()

    st.divider()
    set_results = [compute_set_result(s["player_score"], s["opponent_score"]) for s in set_rows]
    match_result, score_summary = compute_match_result(set_results, max_sets)
    needed = majority_needed(max_sets)
    if match_result == "Incomplete":
        st.info(f"Match so far: **{score_summary}** - needs {needed} set wins to decide.")
    else:
        st.success(f"Match result: **{match_result}** ({score_summary})")

    st.divider()
    duplicate_confirmed = st.session_state.get("mp_confirm_dup", False)
    if st.button("\U0001F4BE Save session", type="primary"):
        if not opponent_name or not opponent_name.strip():
            st.error("Opponent name is required.")
        else:
            existing = db.find_possible_duplicate_match(athlete["id"], match_date, int(match_no), category=category, opponent_name=opponent_name, stage=stage)
            if existing and not duplicate_confirmed:
                st.session_state["mp_confirm_dup"] = True
                st.warning(f"A match already exists for {athlete['name']} on {match_date} with Match No. {int(match_no)}. Click Save again to confirm this is a separate one.")
                st.stop()
            st.session_state["mp_confirm_dup"] = False
            match_id = db.create_match(athlete["id"], entry_type["id"], match_date, category, stage, int(match_no), opponent_name, int(max_sets))
            db.create_match_sets(match_id, set_rows)
            st.success("Session saved.")
            st.session_state.mp_num_sets = 1
            st.rerun()


# =====================================================================
# RSA Test
# =====================================================================
def _render_rsa(sport, entry_type):
    athlete = _athlete_picker(sport)
    st.divider()

    col1, col2 = st.columns(2, gap="large")
    with col1:
        test_date = st.date_input("Date", value=datetime.date.today())
    with col2:
        stages = db.list_stages(entry_type["id"])
        stage = st.selectbox("Stage", [s["name"] for s in stages]) if stages else None

    st.divider()
    st.subheader("Sets (up to 10)")
    if "rsa_num_sets" not in st.session_state:
        st.session_state.rsa_num_sets = 1

    set_rows = []
    for i in range(st.session_state.rsa_num_sets):
        with st.expander(f"Set {i + 1}", expanded=(i == st.session_state.rsa_num_sets - 1)):
            c1, c2 = st.columns(2, gap="large")
            with c1:
                lap1 = st.number_input("Lap 1 (sec)", min_value=0.0, value=None, placeholder="Not entered", key=f"rsa_l1_{i}")
            with c2:
                lap2 = st.number_input("Lap 2 (sec)", min_value=0.0, value=None, placeholder="Not entered", key=f"rsa_l2_{i}")
            if lap1 is not None and lap2 is not None:
                st.caption(f"Total: {lap1 + lap2:.2f}s")
            set_rows.append({"set_no": i + 1, "lap_1": lap1, "lap_2": lap2})

    col1, col2 = st.columns(2, gap="large")
    with col1:
        if st.session_state.rsa_num_sets < 10:
            if st.button("\u2795 Add another set"):
                st.session_state.rsa_num_sets += 1
                st.rerun()
    with col2:
        if st.session_state.rsa_num_sets > 1:
            if st.button("\u2796 Remove last set"):
                st.session_state.rsa_num_sets -= 1
                st.rerun()

    st.divider()
    if st.button("\U0001F4BE Save test", type="primary"):
        valid_sets = [s for s in set_rows if s["lap_1"] is not None and s["lap_2"] is not None]
        if not valid_sets:
            st.error("Enter at least one complete set (both laps) before saving.")
        else:
            test_id = db.create_rsa_test(athlete["id"], entry_type["id"], test_date, stage)
            db.create_rsa_sets(test_id, valid_sets)
            st.success("Test saved.")
            st.session_state.rsa_num_sets = 1
            st.rerun()


# =====================================================================
# YIRC L1
# =====================================================================
def _render_yoyo(sport, entry_type):
    athlete = _athlete_picker(sport)
    if not athlete.get("gender"):
        st.warning(f"{athlete['name']} doesn't have a gender set. Ratings won't show until it's fixed in Admin.")
    st.divider()

    col1, col2, col3 = st.columns(3, gap="large")
    with col1:
        test_date = st.date_input("Date", value=datetime.date.today())
    with col2:
        stages = db.list_stages(entry_type["id"])
        stage = st.selectbox("Stage", [s["name"] for s in stages]) if stages else None
    with col3:
        age = st.number_input("Age", min_value=0, max_value=100, value=None, placeholder="Not entered")

    st.subheader("Test result")
    col1, col2, col3 = st.columns(3, gap="large")
    with col1:
        level = st.number_input("Level reached", min_value=1, max_value=25, value=15)
    with col2:
        shuttle = st.number_input("Shuttle reached", min_value=0, max_value=20, value=1)
    with col3:
        peak_hr = st.number_input("Peak HR (bpm)", min_value=0, value=None, placeholder="Not entered")

    score = compute_score(int(level), int(shuttle))
    distance = compute_distance(int(level), int(shuttle))
    vo2max = compute_vo2max(distance)
    rating = rate_score(score, athlete.get("gender"))
    c1, c2, c3 = st.columns(3, gap="large")
    c1.metric("Score", f"{score}")
    c2.metric("Distance", f"{distance:.0f} m")
    c3.metric("Est. VO2max", f"{vo2max:.1f} ml/kg/min")
    if rating:
        st.caption(f"Rating: **{rating}**")

    st.divider()
    st.subheader("Blood lactate (mmol/L)")
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7, gap="large")
    with c1:
        lac_pre = st.number_input("Pre-Test", min_value=0.0, value=None, placeholder="-", key="lac_pre")
    with c2:
        lac_peak = st.number_input("Peak", min_value=0.0, value=None, placeholder="-", key="lac_peak")
    with c3:
        lac_0 = st.number_input("0 min", min_value=0.0, value=None, placeholder="-", key="lac_0")
    with c4:
        lac_2 = st.number_input("2 min", min_value=0.0, value=None, placeholder="-", key="lac_2")
    with c5:
        lac_5 = st.number_input("5 min", min_value=0.0, value=None, placeholder="-", key="lac_5")
    with c6:
        lac_7 = st.number_input("7 min", min_value=0.0, value=None, placeholder="-", key="lac_7")
    with c7:
        lac_9 = st.number_input("9 min", min_value=0.0, value=None, placeholder="-", key="lac_9")

    st.divider()
    if st.button("\U0001F4BE Save test", type="primary"):
        payload = {
            "athlete_id": athlete["id"], "entry_type_id": entry_type["id"], "test_date": str(test_date),
            "stage": stage, "age": int(age) if age is not None else None,
            "level": int(level), "shuttle": int(shuttle), "peak_hr": int(peak_hr) if peak_hr is not None else None,
            "lactate_pretest": lac_pre, "lactate_peak": lac_peak, "lactate_0min": lac_0,
            "lactate_2min": lac_2, "lactate_5min": lac_5, "lactate_7min": lac_7, "lactate_9min": lac_9,
        }
        db.create_yoyo_test(payload)
        st.success("Test saved.")
        st.rerun()


# =====================================================================
# Long Jump Test
# =====================================================================
def _render_longjump(sport, entry_type):
    athlete = _athlete_picker(sport)
    st.divider()
    test_date = st.date_input("Date", value=datetime.date.today())

    st.divider()
    st.subheader("Jumps")
    if "lj_num_jumps" not in st.session_state:
        st.session_state.lj_num_jumps = 1

    jump_rows = []
    for i in range(st.session_state.lj_num_jumps):
        with st.expander(f"Jump {i + 1}", expanded=(i == st.session_state.lj_num_jumps - 1)):
            c1, c2, c3 = st.columns(3, gap="large")
            with c1:
                first_10m = st.number_input("First 10m (s)", min_value=0.0, value=None, placeholder="Not entered", key=f"lj_10_{i}")
            with c2:
                split_10_15 = st.number_input("10-15m Split (s)", min_value=0.0, value=None, placeholder="Not entered", key=f"lj_1015_{i}")
            with c3:
                split_15_20 = st.number_input("15-20m Split (s)", min_value=0.0, value=None, placeholder="Not entered", key=f"lj_1520_{i}")

            if first_10m is not None and split_10_15 is not None and split_15_20 is not None:
                v = compute_attempt_velocities(first_10m, split_10_15, split_15_20)
                total = compute_total_time(first_10m, split_10_15, split_15_20)
                st.caption(f"Total: {total:.3f}s | Velocities: {v['v_0_10']} / {v['v_10_15']} / {v['v_15_20']} m/s")

            c1, c2 = st.columns(2, gap="large")
            with c1:
                validity = st.selectbox("Validity", ["Valid", "Invalid", "N/A"], index=0, key=f"lj_valid_{i}")
            with c2:
                jump_length = st.number_input("Jump Length (m, optional)", min_value=0.0, value=None, placeholder="Not entered", key=f"lj_len_{i}")

            jump_rows.append({
                "jump_no": i + 1, "first_10m": first_10m, "split_10_15": split_10_15, "split_15_20": split_15_20,
                "total_time": compute_total_time(first_10m, split_10_15, split_15_20) if first_10m is not None and split_10_15 is not None and split_15_20 is not None else None,
                "validity": validity, "jump_length": jump_length,
            })

    col1, col2 = st.columns(2, gap="large")
    with col1:
        if st.button("\u2795 Add another jump"):
            st.session_state.lj_num_jumps += 1
            st.rerun()
    with col2:
        if st.session_state.lj_num_jumps > 1:
            if st.button("\u2796 Remove last jump"):
                st.session_state.lj_num_jumps -= 1
                st.rerun()

    st.divider()
    if st.button("\U0001F4BE Save test", type="primary"):
        valid_jumps = [j for j in jump_rows if j["first_10m"] is not None and j["split_10_15"] is not None and j["split_15_20"] is not None]
        if not valid_jumps:
            st.error("Enter at least one complete jump before saving.")
        else:
            test_id = db.create_longjump_test(athlete["id"], entry_type["id"], test_date)
            db.create_longjump_attempts(test_id, valid_jumps)
            st.success("Test saved.")
            st.session_state.lj_num_jumps = 1
            st.rerun()


# =====================================================================
# Judo Fitness Test
# =====================================================================
def _judo_bilateral_grid(measure_key, label, unit):
    """Three trials x Right/Left for one handgrip measure. Returns
    {trial_no: {"<measure>_right": v, "<measure>_left": v}}."""
    st.markdown(f"**{label}** ({unit})")
    out = {}
    cols = st.columns(N_TRIALS * 2, gap="medium")
    for i in range(N_TRIALS):
        with cols[i * 2]:
            r = st.number_input(f"Trial {i + 1} - Right", min_value=0.0, value=None, placeholder="-", key=f"judo_{measure_key}_r_{i}")
        with cols[i * 2 + 1]:
            l = st.number_input(f"Trial {i + 1} - Left", min_value=0.0, value=None, placeholder="-", key=f"judo_{measure_key}_l_{i}")
        out[i + 1] = {f"{measure_key}_right": r, f"{measure_key}_left": l}
    return out


def _render_judo(sport, entry_type):
    athlete = _athlete_picker(sport)
    st.divider()

    col1, col2, col3 = st.columns(3, gap="large")
    with col1:
        test_date = st.date_input("Date", value=datetime.date.today())
    with col2:
        stages = db.list_stages(entry_type["id"])
        stage = st.selectbox("Stage", [s["name"] for s in stages]) if stages else None
    with col3:
        body_mass = st.number_input("Body mass (kg)", min_value=0.0, value=None, placeholder="Required", step=0.05, format="%.2f")

    # ---------- Handgrip dynamometer ----------
    st.divider()
    st.subheader("Handgrip dynamometer")
    trials = {i + 1: {"trial_no": i + 1} for i in range(N_TRIALS)}
    for key, label, unit in [("grip", "Peak Force", "N"), ("max_rfd", "Max RFD", "N/s"), ("avg_rfd", "Average RFD", "N/s")]:
        for trial_no, vals in _judo_bilateral_grid(key, label, unit).items():
            trials[trial_no].update(vals)

    # ---------- IMTP ----------
    st.divider()
    st.subheader("Isometric mid-thigh pull (IMTP)")
    cols = st.columns(N_TRIALS, gap="large")
    for i, col in enumerate(cols):
        with col:
            trials[i + 1]["imtp_peak"] = st.number_input(f"Trial {i + 1} - Peak Force (N)", min_value=0.0, value=None, placeholder="-", key=f"judo_imtp_{i}")

    # ---------- 1-min ramp ----------
    st.divider()
    st.subheader("1-min ramp test (rowing ergometer)")
    c1, c2, c3, c4 = st.columns(4, gap="large")
    with c1:
        last_watt = st.number_input("Last watt (W)", min_value=0.0, value=None, placeholder="-")
    with c2:
        duration = st.number_input("Duration to exhaustion (s)", min_value=0.0, max_value=60.0, value=None, placeholder="-",
                                    help="Seconds completed in the final, unfinished 1-min step.")
    with c3:
        increment = st.number_input("Increment (W)", min_value=0.0, value=25.0)
    with c4:
        peak_hr = st.number_input("Peak HR (bpm)", min_value=0, value=None, placeholder="-")

    trial_rows = list(trials.values())
    gender = athlete.get("gender")
    preview = judo_summarize({
        "trials": trial_rows, "body_mass": body_mass, "ramp_last_watt": last_watt,
        "ramp_duration_s": duration, "ramp_increment": increment, "ramp_peak_hr": peak_hr,
    }, gender=gender)
    st.divider()
    c1, c2, c3, c4 = st.columns(4, gap="large")
    c1.metric("Best IMTP", f"{preview['imtp_best']:,.0f} N" if preview["imtp_best"] is not None else "-")
    c2.metric("Relative IMTP", f"{preview['imtp_rel']:.2f} N/kg" if preview["imtp_rel"] is not None else "-")
    c3.metric("Peak Power", f"{preview['peak_power']:.1f} W" if preview["peak_power"] is not None else "-")
    c4.metric("Predicted VO2max", f"{preview['vo2max']:.1f} ml/kg/min" if preview["vo2max"] is not None else "-")
    parts = []
    if preview["grip_asym"] is not None:
        parts.append(f"Grip asymmetry: **{preview['grip_asym']:.1f}%**" + (f" (trial CV {preview['grip_cv']:.1f}%)" if preview["grip_cv"] is not None else ""))
    if preview["rfd_asym"] is not None:
        parts.append(f"Max RFD asymmetry: **{preview['rfd_asym']:.1f}%**" + (f" (trial CV {preview['rfd_cv']:.1f}%)" if preview["rfd_cv"] is not None else ""))
    if parts:
        st.caption(" | ".join(parts))

    for w in judo_entry_checks(trial_rows, duration, last_watt):
        st.warning(w)

    st.divider()
    if st.button("\U0001F4BE Save test", type="primary"):
        filled = [t for t in trial_rows if any(v is not None for k, v in t.items() if k != "trial_no")]
        if not body_mass:
            st.error("Body mass is required - relative force, power/kg and VO2max all depend on it.")
        elif not filled and last_watt is None:
            st.error("Enter at least one handgrip/IMTP trial or the ramp test result before saving.")
        else:
            test_id = db.create_judo_test({
                "athlete_id": athlete["id"], "entry_type_id": entry_type["id"], "test_date": str(test_date),
                "stage": stage, "body_mass": body_mass, "ramp_last_watt": last_watt,
                "ramp_duration_s": duration, "ramp_increment": increment,
                "ramp_peak_hr": int(peak_hr) if peak_hr is not None else None,
            })
            db.create_judo_trials(test_id, filled)
            st.success("Test saved.")
            st.rerun()
