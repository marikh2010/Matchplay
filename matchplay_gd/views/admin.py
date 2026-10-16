import streamlit as st
import db
from style import apply_style


def render():
    apply_style()
    st.title("\U0001F6E0\uFE0F Admin")
    st.caption("No login needed - open to anyone with the app link.")

    tab_athletes, tab_stages, tab_sessions = st.tabs(["Athletes", "Stages", "Sessions"])
    with tab_athletes:
        _render_athletes_tab()
    with tab_stages:
        _render_stages_tab()
    with tab_sessions:
        _render_sessions_tab()


def _render_athletes_tab():
    st.subheader("Athletes")
    sports = db.list_sports()
    if not sports:
        st.info("Add a sport first.")
        return

    sport_lookup = {s["name"]: s["id"] for s in sports}
    ath_sport_name = st.selectbox("Sport", list(sport_lookup.keys()), key="athlete_mgmt_sport")
    ath_sport_id = sport_lookup[ath_sport_name]

    athletes = db.list_athletes(sport_id=ath_sport_id)
    if athletes:
        gender_options = ["Male", "Female"]
        for a in athletes:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 1.2, 0.7, 0.7], gap="large")
                with c1:
                    new_name = st.text_input("Name", value=a["name"], key=f"athname_{a['id']}", label_visibility="collapsed")
                with c2:
                    current_gender = a.get("gender")
                    new_gender = st.selectbox(
                        "Gender", gender_options,
                        index=gender_options.index(current_gender) if current_gender in gender_options else 0,
                        key=f"athgender_{a['id']}", label_visibility="collapsed",
                    )
                with c3:
                    if st.button("Save", key=f"saveath_{a['id']}"):
                        try:
                            db.update_athlete(a["id"], new_name.strip(), new_gender)
                            st.success("Saved.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                with c4:
                    if st.button("Delete", key=f"delath_{a['id']}"):
                        db.delete_athlete(a["id"])
                        st.success("Deleted (and all their matches/tests).")
                        st.rerun()
    else:
        st.info(f"No athletes added yet for {ath_sport_name}.")

    with st.form("add_athlete_form", clear_on_submit=True):
        st.write(f"Add a new athlete to {ath_sport_name}")
        col1, col2 = st.columns([2, 1], gap="large")
        with col1:
            new_athlete_name = st.text_input("Athlete name")
        with col2:
            new_athlete_gender = st.selectbox("Gender", ["Male", "Female"])
        if st.form_submit_button("Add athlete"):
            if not new_athlete_name.strip():
                st.error("Athlete name can't be empty.")
            elif any(a["name"].strip().lower() == new_athlete_name.strip().lower() for a in athletes):
                st.error(f"'{new_athlete_name.strip()}' is already added for {ath_sport_name}.")
            else:
                try:
                    db.create_athlete(new_athlete_name.strip(), ath_sport_id, new_athlete_gender)
                    st.success(f"Added '{new_athlete_name}'.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


def _render_stages_tab():
    st.subheader("Stages")
    st.caption("Options shown in the Data Entry Stage dropdown, per entry type.")
    sports = db.list_sports()
    if not sports:
        st.info("Add a sport first.")
        return

    sport_lookup = {s["name"]: s["id"] for s in sports}
    stage_sport_name = st.selectbox("Sport", list(sport_lookup.keys()), key="stage_mgmt_sport")
    stage_entry_types = db.list_entry_types(sport_lookup[stage_sport_name])
    if not stage_entry_types:
        st.info("No entry types yet for this sport.")
        return

    et_names = [et["name"] for et in stage_entry_types]
    stage_et_name = st.selectbox("Entry Type", et_names, key="stage_mgmt_et")
    stage_et = next(et for et in stage_entry_types if et["name"] == stage_et_name)

    stages = db.list_stages(stage_et["id"])
    if stages:
        for stg in stages:
            c1, c2 = st.columns([4, 1], gap="large")
            with c1:
                st.write(stg["name"])
            with c2:
                if st.button("Remove", key=f"delstage_{stg['id']}"):
                    db.delete_stage(stg["id"])
                    st.rerun()
    else:
        st.info(f"No stages added yet for {stage_et_name}.")

    with st.form("add_stage_form", clear_on_submit=True):
        st.write(f"Add a new stage to {stage_et_name}")
        new_stage_name = st.text_input("Stage name")
        if st.form_submit_button("Add stage"):
            if not new_stage_name.strip():
                st.error("Stage name can't be empty.")
            else:
                try:
                    next_order = (max([s["sort_order"] for s in stages]) + 1) if stages else 1
                    db.create_stage(stage_et["id"], new_stage_name.strip(), next_order)
                    st.success(f"Added '{new_stage_name}'.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


def _render_sessions_tab():
    st.subheader("Entered sessions")
    st.caption("Edit or delete individual entries.")

    sports = db.list_sports()
    if not sports:
        st.info("Add a sport first.")
        return

    sport_lookup = {s["name"]: s["id"] for s in sports}
    sess_sport_name = st.selectbox("Sport", list(sport_lookup.keys()), key="sess_mgmt_sport")
    sess_entry_types = db.list_entry_types(sport_lookup[sess_sport_name])
    if not sess_entry_types:
        st.info("No entry types yet for this sport.")
        return

    et_names = [et["name"] for et in sess_entry_types]
    sess_et_name = st.selectbox("Entry Type", et_names, key="sess_mgmt_et")

    if sess_et_name == "Match Play":
        _render_match_rows()
    elif sess_et_name == "RSA Test":
        _render_rsa_rows()
    elif sess_et_name == "Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test":
        _render_yoyo_rows()
    elif sess_et_name == "Long Jump Test":
        _render_longjump_rows()
    elif sess_et_name == "Judo Fitness Test":
        _render_judo_rows(next(et for et in sess_entry_types if et["name"] == sess_et_name))
    else:
        st.info(f"No entries view built for '{sess_et_name}' yet.")


def _render_match_rows():
    matches = db.get_matches()
    if not matches:
        st.info("No matches logged yet.")
        return
    stage_options = ["Training"] + [s["name"] for et in db.list_entry_types(matches[0]["athletes"]["sport_id"]) if et["name"] == "Match Play" for s in db.list_stages(et["id"])]
    for m in matches:
        with st.expander(f"{m['match_date']} \u00B7 {m['athletes']['name']} \u00B7 vs {m['opponent_name']} \u00B7 {m['category']}"):
            c1, c2, c3, c4 = st.columns(4, gap="large")
            with c1:
                category = st.selectbox("Category", ["Training", "Tournament"], index=0 if m["category"] == "Training" else 1, key=f"m_cat_{m['id']}")
            with c2:
                stage_idx = stage_options.index(m["stage"]) if m["stage"] in stage_options else 0
                stage = st.selectbox("Stage", stage_options, index=stage_idx, key=f"m_stage_{m['id']}")
            with c3:
                opponent = st.text_input("Opponent", value=m["opponent_name"] or "", key=f"m_opp_{m['id']}")
            with c4:
                match_no = st.number_input("Match No", min_value=1, value=m["match_no"], key=f"m_no_{m['id']}")

            sets = db.get_match_sets(m["id"])
            for s in sets:
                sc1, sc2, sc3 = st.columns([1, 1, 1], gap="large")
                with sc1:
                    st.caption(f"Set {s['set_no']}")
                with sc2:
                    ps = st.number_input("Player", min_value=0, value=s["player_score"] or 0, key=f"m_ps_{s['id']}", label_visibility="collapsed")
                with sc3:
                    os_ = st.number_input("Opponent", min_value=0, value=s["opponent_score"] or 0, key=f"m_os_{s['id']}", label_visibility="collapsed")
                if st.button("Save set", key=f"m_saveset_{s['id']}"):
                    db.update_match_set_scores(s["id"], ps, os_)
                    st.success("Set saved.")
                    st.rerun()

            c1, c2 = st.columns(2, gap="large")
            with c1:
                if st.button("Save match details", key=f"m_save_{m['id']}"):
                    db.update_match(m["id"], category, stage, opponent.strip(), int(match_no))
                    st.success("Saved.")
                    st.rerun()
            with c2:
                if st.button("Delete entire match", key=f"m_del_{m['id']}"):
                    db.delete_match(m["id"])
                    st.success("Deleted.")
                    st.rerun()


def _render_rsa_rows():
    tests = db.get_rsa_tests_with_sets()
    if not tests:
        st.info("No RSA tests logged yet.")
        return
    for t in tests:
        with st.expander(f"{t['test_date']} \u00B7 {t['athletes']['name']} \u00B7 {t['stage'] or ''}"):
            stage = st.selectbox("Stage", ["Pre", "Post"], index=0 if (t["stage"] or "Pre") == "Pre" else 1, key=f"r_stage_{t['id']}")
            for s in t["sets"]:
                c1, c2, c3 = st.columns([1, 1, 1], gap="large")
                with c1:
                    st.caption(f"Set {s['set_no']}")
                with c2:
                    l1 = st.number_input("Lap 1", min_value=0.0, value=float(s["lap_1"]), key=f"r_l1_{s['id']}", label_visibility="collapsed")
                with c3:
                    l2 = st.number_input("Lap 2", min_value=0.0, value=float(s["lap_2"]), key=f"r_l2_{s['id']}", label_visibility="collapsed")
                if st.button("Save set", key=f"r_saveset_{s['id']}"):
                    db.update_rsa_set(s["id"], l1, l2)
                    st.success("Set saved.")
                    st.rerun()

            c1, c2 = st.columns(2, gap="large")
            with c1:
                if st.button("Save stage", key=f"r_save_{t['id']}"):
                    db.update_rsa_test(t["id"], stage)
                    st.success("Saved.")
                    st.rerun()
            with c2:
                if st.button("Delete entire test", key=f"r_del_{t['id']}"):
                    db.delete_rsa_test(t["id"])
                    st.success("Deleted.")
                    st.rerun()


def _render_yoyo_rows():
    tests = db.get_yoyo_tests()
    if not tests:
        st.info("No Yo-Yo tests logged yet.")
        return
    for t in tests:
        with st.expander(f"{t['test_date']} \u00B7 {t['athletes']['name']} \u00B7 Level {t['level']}.{t['shuttle']}"):
            c1, c2, c3 = st.columns(3, gap="large")
            with c1:
                level = st.number_input("Level", min_value=1, value=t["level"], key=f"y_level_{t['id']}")
                shuttle = st.number_input("Shuttle", min_value=0, value=t["shuttle"], key=f"y_shuttle_{t['id']}")
            with c2:
                peak_hr = st.number_input("Peak HR", min_value=0, value=t.get("peak_hr") or 0, key=f"y_hr_{t['id']}")
                age = st.number_input("Age", min_value=0, value=t.get("age") or 0, key=f"y_age_{t['id']}")
            with c3:
                stage = st.selectbox("Stage", ["Pre", "Post"], index=0 if (t.get("stage") or "Pre") == "Pre" else 1, key=f"y_stage_{t['id']}")

            st.caption("Blood lactate")
            lc = st.columns(7, gap="large")
            keys = ["lactate_pretest", "lactate_peak", "lactate_0min", "lactate_2min", "lactate_5min", "lactate_7min", "lactate_9min"]
            labels = ["Pre", "Peak", "0m", "2m", "5m", "7m", "9m"]
            lac_vals = {}
            for col, key, label in zip(lc, keys, labels):
                with col:
                    lac_vals[key] = st.number_input(label, min_value=0.0, value=float(t.get(key) or 0), key=f"y_{key}_{t['id']}")

            c1, c2 = st.columns(2, gap="large")
            with c1:
                if st.button("Save test", key=f"y_save_{t['id']}"):
                    payload = {"level": int(level), "shuttle": int(shuttle), "peak_hr": int(peak_hr) or None,
                               "age": int(age) or None, "stage": stage, **lac_vals}
                    db.update_yoyo_test(t["id"], payload)
                    st.success("Saved.")
                    st.rerun()
            with c2:
                if st.button("Delete test", key=f"y_del_{t['id']}"):
                    db.delete_yoyo_test(t["id"])
                    st.success("Deleted.")
                    st.rerun()


def _render_longjump_rows():
    tests = db.get_longjump_tests_with_attempts()
    if not tests:
        st.info("No Long Jump tests logged yet.")
        return
    for t in tests:
        with st.expander(f"{t['test_date']} \u00B7 {t['athletes']['name']} \u00B7 {len(t['attempts'])} jump(s)"):
            for a in t["attempts"]:
                st.caption(f"Jump {a['jump_no']}")
                c1, c2, c3, c4, c5 = st.columns(5, gap="large")
                with c1:
                    f10 = st.number_input("First 10m", min_value=0.0, value=float(a["first_10m"]), key=f"lj_10_{a['id']}", label_visibility="collapsed")
                with c2:
                    s1015 = st.number_input("10-15m", min_value=0.0, value=float(a["split_10_15"]), key=f"lj_1015_{a['id']}", label_visibility="collapsed")
                with c3:
                    s1520 = st.number_input("15-20m", min_value=0.0, value=float(a["split_15_20"]), key=f"lj_1520_{a['id']}", label_visibility="collapsed")
                with c4:
                    validity_options = ["Valid", "Invalid", "N/A"]
                    v_idx = validity_options.index(a["validity"]) if a["validity"] in validity_options else 2
                    validity = st.selectbox("Validity", validity_options, index=v_idx, key=f"lj_valid_{a['id']}", label_visibility="collapsed")
                with c5:
                    length = st.number_input("Length", min_value=0.0, value=float(a.get("jump_length") or 0), key=f"lj_len_{a['id']}", label_visibility="collapsed")
                if st.button("Save jump", key=f"lj_savejump_{a['id']}"):
                    db.update_longjump_attempt(a["id"], f10, s1015, s1520, validity, length or None)
                    st.success("Jump saved.")
                    st.rerun()

            if st.button("Delete entire test", key=f"lj_del_{t['id']}"):
                db.delete_longjump_test(t["id"])
                st.success("Deleted.")
                st.rerun()


def _render_judo_rows(entry_type):
    tests = db.get_judo_tests_with_trials()
    if not tests:
        st.info("No Judo Fitness Tests logged yet.")
        return
    stage_options = [s["name"] for s in db.list_stages(entry_type["id"])] or ["Pre", "Post"]
    trial_fields = [
        ("grip_right", "Grip R"), ("grip_left", "Grip L"), ("max_rfd_right", "Max RFD R"), ("max_rfd_left", "Max RFD L"),
        ("avg_rfd_right", "Avg RFD R"), ("avg_rfd_left", "Avg RFD L"), ("imtp_peak", "IMTP"),
    ]

    def _num(label, value, key, **kw):
        return st.number_input(label, min_value=0.0, value=float(value) if value is not None else None, placeholder="-", key=key, **kw)

    for t in tests:
        with st.expander(f"{t['test_date']} \u00B7 {t['athletes']['name']} \u00B7 {t.get('stage') or ''}"):
            c1, c2, c3 = st.columns(3, gap="large")
            with c1:
                idx = stage_options.index(t["stage"]) if t.get("stage") in stage_options else 0
                stage = st.selectbox("Stage", stage_options, index=idx, key=f"j_stage_{t['id']}")
            with c2:
                mass = _num("Body mass (kg)", t.get("body_mass"), f"j_mass_{t['id']}")
            with c3:
                peak_hr = st.number_input("Peak HR", min_value=0, value=t.get("ramp_peak_hr"), placeholder="-", key=f"j_hr_{t['id']}")
            c1, c2, c3 = st.columns(3, gap="large")
            with c1:
                last_watt = _num("Last watt (W)", t.get("ramp_last_watt"), f"j_lw_{t['id']}")
            with c2:
                duration = _num("Duration to exhaustion (s)", t.get("ramp_duration_s"), f"j_dur_{t['id']}")
            with c3:
                increment = _num("Increment (W)", t.get("ramp_increment"), f"j_inc_{t['id']}")

            st.caption("Trials")
            hdr = st.columns([0.6] + [1] * len(trial_fields), gap="small")
            for col, (_, label) in zip(hdr[1:], trial_fields):
                col.caption(label)
            trial_edits = {}
            for tr in t["trials"]:
                cols = st.columns([0.6] + [1] * len(trial_fields), gap="small")
                cols[0].caption(f"T{tr['trial_no']}")
                vals = {}
                for col, (key, label) in zip(cols[1:], trial_fields):
                    with col:
                        vals[key] = _num(label, tr.get(key), f"j_{key}_{tr['id']}", label_visibility="collapsed")
                trial_edits[tr["id"]] = vals

            c1, c2 = st.columns(2, gap="large")
            with c1:
                if st.button("Save test", key=f"j_save_{t['id']}"):
                    if not mass:
                        st.error("Body mass is required.")
                    else:
                        db.update_judo_test(t["id"], {
                            "stage": stage, "body_mass": mass, "ramp_peak_hr": int(peak_hr) if peak_hr is not None else None,
                            "ramp_last_watt": last_watt, "ramp_duration_s": duration, "ramp_increment": increment,
                        })
                        for trial_id, vals in trial_edits.items():
                            db.update_judo_trial(trial_id, vals)
                        st.success("Saved.")
                        st.rerun()
            with c2:
                if st.button("Delete entire test", key=f"j_del_{t['id']}"):
                    db.delete_judo_test(t["id"])
                    st.success("Deleted.")
                    st.rerun()
