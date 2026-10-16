import io
import streamlit as st
import pandas as pd
import db
from match_logic import compute_set_result, compute_match_result
from yoyo_logic import compute_score, compute_distance, compute_vo2max
from longjump_logic import compute_attempt_velocities, compute_total_time
from judo_logic import summarize as judo_summarize
from style import apply_style


def render():
    st.title("\U0001F4E4 Preview & export")
    st.write("Preview everything entered and download it as an Excel file.")

    sports = db.list_sports()
    if not sports:
        apply_style()
        st.info("No data yet.")
        st.stop()

    sport_lookup = {s["name"]: s for s in sports}
    col1, col2 = st.columns(2, gap="large")
    with col1:
        sport_name = st.selectbox("Sport", list(sport_lookup.keys()))
    sport = sport_lookup[sport_name]
    apply_style(sport_name)

    entry_types = db.list_entry_types(sport["id"])
    if not entry_types:
        st.info("No entry types set up for this sport yet.")
        st.stop()
    with col2:
        et_name = st.selectbox("Entry Type", [et["name"] for et in entry_types])

    if et_name == "Match Play":
        df = _matchplay_rows()
    elif et_name == "RSA Test":
        df = _rsa_rows()
    elif et_name == "Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test":
        df = _yoyo_rows()
    elif et_name == "Long Jump Test":
        df = _longjump_rows()
    elif et_name == "Judo Fitness Test":
        df = _judo_rows()
    else:
        st.info(f"No export built for '{et_name}' yet.")
        st.stop()

    if df.empty:
        st.info("No sessions match these filters.")
        st.stop()

    st.caption(f"{len(df)} rows")
    st.table(df.to_dict(orient="records"))

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=et_name[:31])
    buffer.seek(0)
    st.download_button("\u2B07\uFE0F Download as Excel", data=buffer, file_name=f"{et_name.lower().replace(' ', '_')}_export.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _matchplay_rows():
    matches = db.get_matches()
    rows = []
    for m in matches:
        sets = db.get_match_sets(m["id"])
        set_results = [compute_set_result(s["player_score"], s["opponent_score"]) for s in sets]
        match_result, score_summary = compute_match_result(set_results, m["max_sets"])
        for s in sets:
            row = {
                "Date": m["match_date"], "Athlete": m["athletes"]["name"], "Category": m["category"],
                "Stage": m["stage"], "Match No": m["match_no"], "Opponent": m["opponent_name"],
                "Match Format": f"Best of {m['max_sets']}", "Match Result": match_result, "Match Score": score_summary,
            }
            row.update({k: v for k, v in s.items() if k not in ("id", "match_id", "created_at")})
            rows.append(row)
    return pd.DataFrame(rows)


def _rsa_rows():
    tests = db.get_rsa_tests_with_sets()
    rows = []
    for t in tests:
        for s in t["sets"]:
            rows.append({
                "Date": t["test_date"], "Athlete": t["athletes"]["name"], "Stage": t["stage"],
                "Set": s["set_no"], "Lap 1": s["lap_1"], "Lap 2": s["lap_2"], "Total": s["lap_1"] + s["lap_2"],
            })
    return pd.DataFrame(rows)


def _yoyo_rows():
    tests = db.get_yoyo_tests()
    rows = []
    for t in tests:
        distance = compute_distance(t["level"], t["shuttle"])
        rows.append({
            "Date": t["test_date"], "Athlete": t["athletes"]["name"], "Gender": t["athletes"].get("gender"),
            "Age": t.get("age"), "Stage": t.get("stage"), "Score": compute_score(t["level"], t["shuttle"]),
            "Distance (m)": distance, "Est. VO2max": compute_vo2max(distance), "Peak HR": t.get("peak_hr"),
            "Lactate Pre-Test": t.get("lactate_pretest"), "Lactate Peak": t.get("lactate_peak"),
            "Lactate 0min": t.get("lactate_0min"), "Lactate 2min": t.get("lactate_2min"),
            "Lactate 5min": t.get("lactate_5min"), "Lactate 7min": t.get("lactate_7min"), "Lactate 9min": t.get("lactate_9min"),
        })
    return pd.DataFrame(rows)


def _longjump_rows():
    tests = db.get_longjump_tests_with_attempts()
    rows = []
    for t in tests:
        for a in t["attempts"]:
            v = compute_attempt_velocities(a["first_10m"], a["split_10_15"], a["split_15_20"])
            rows.append({
                "Date": t["test_date"], "Athlete": t["athletes"]["name"], "Jump": a["jump_no"],
                "First 10m (s)": a["first_10m"], "10-15m Split (s)": a["split_10_15"], "15-20m Split (s)": a["split_15_20"],
                "Total Time (s)": compute_total_time(a["first_10m"], a["split_10_15"], a["split_15_20"]),
                "V 0-10m (m/s)": v["v_0_10"], "V 10-15m (m/s)": v["v_10_15"], "V 15-20m (m/s)": v["v_15_20"],
                "Validity": a.get("validity"), "Jump Length (m)": a.get("jump_length"),
            })
    return pd.DataFrame(rows)


def _judo_rows():
    tests = db.get_judo_tests_with_trials()
    rows = []
    for t in tests:
        m = judo_summarize(t)
        row = {
            "Date": t["test_date"], "Athlete": t["athletes"]["name"], "Stage": t.get("stage"),
            "Body Mass (kg)": t.get("body_mass"),
        }
        by_no = {tr["trial_no"]: tr for tr in t["trials"]}
        for label, key in [("Grip", "grip"), ("Max RFD", "max_rfd"), ("Avg RFD", "avg_rfd")]:
            for n in (1, 2, 3):
                for side, s in (("R", "right"), ("L", "left")):
                    row[f"{label} T{n} {side}"] = by_no.get(n, {}).get(f"{key}_{s}")
        for n in (1, 2, 3):
            row[f"IMTP T{n} (N)"] = by_no.get(n, {}).get("imtp_peak")
        row.update({
            "Last Watt (W)": t.get("ramp_last_watt"),
            "Duration to Exhaustion (s)": t.get("ramp_duration_s"), "Ramp Increment (W)": t.get("ramp_increment"),
            "Peak HR": t.get("ramp_peak_hr"), "Gender": m["gender"],
            "Grip Best R (N)": m["grip_best_right"], "Grip Best L (N)": m["grip_best_left"],
            "Grip Best R (kgf)": m["grip_best_right_kgf"], "Grip Best L (kgf)": m["grip_best_left_kgf"],
            "Grip Rating R (Franchini 2018)": m["grip_rating_right"], "Grip Rating L (Franchini 2018)": m["grip_rating_left"],
            "Grip Allometric (N/kg^0.67)": m["grip_allo"],
            "Grip Asymmetry (%)": m["grip_asym"], "Grip Trial CV (%)": m["grip_cv"],
            "Max RFD Best R": m["rfd_best_right"], "Max RFD Best L": m["rfd_best_left"],
            "Max RFD Asymmetry (%)": m["rfd_asym"], "Max RFD Trial CV (%)": m["rfd_cv"],
            "IMTP Best (N)": m["imtp_best"], "IMTP Ratio (N/kg)": m["imtp_rel"], "IMTP Allometric (N/kg^0.67)": m["imtp_allo"],
            "IMTP Trial Spread (N)": m["imtp_spread"],
            "Peak Power (W)": m["peak_power"], "Peak Power (W/kg)": m["power_per_kg"],
            "Predicted VO2max (mL/kg/min)": m["vo2max"],
        })
        rows.append(row)
    return pd.DataFrame(rows)
