import streamlit as st
import plotly.graph_objects as go
import db
from yoyo_logic import (
    compute_distance, compute_vo2max, compute_score, rate_score,
    estimate_hr_max,
)
from style import COLORS, PLOT_COLORS, CHART_LAYOUT, get_brand_color, render_metric_row
from report_export import ReportBuilder


# Muted six-tier rating palette to suit the dashboard's restrained styling.
RATING_COLOR = {
    "Elite": "#4F9BC7", "Excellent": "#60B77A", "Good": "#A4BE55",
    "Average": "#D9B84E", "Below Average": "#D99352", "Very Poor": "#CF7474",
    None: COLORS["muted"],
}
RATING_ORDER = ["Elite", "Excellent", "Good", "Average", "Below Average", "Very Poor"]
_BAND_TEXT = {
    "Male": {"Elite": "> 20.1", "Excellent": "18.7-20.1", "Good": "17.3-18.6",
             "Average": "15.7-17.2", "Below Average": "14.2-15.6", "Very Poor": "< 14.2"},
    "Female": {"Elite": "> 17.5", "Excellent": "16.6-17.5", "Good": "15.6-16.5",
               "Average": "14.6-15.5", "Below Average": "13.1-14.5", "Very Poor": "< 13.1"},
}
_BAND_LOW_DIST = {
    "Male": {"Elite": compute_distance(20, 1), "Excellent": compute_distance(18, 7), "Good": compute_distance(17, 3),
             "Average": compute_distance(15, 7), "Below Average": compute_distance(14, 2), "Very Poor": 0},
    "Female": {"Elite": compute_distance(17, 5), "Excellent": compute_distance(16, 6), "Good": compute_distance(15, 6),
               "Average": compute_distance(14, 6), "Below Average": compute_distance(13, 1), "Very Poor": 0},
}
_LADDER_MAX = {"Male": compute_distance(22, 0), "Female": compute_distance(19, 0)}
# Only genuinely time-stamped points go on the recovery curve. Peak is
# handled separately since it has no real elapsed-time value.
RECOVERY_CURVE_POINTS = [
    ("Pre-Test", "lactate_pretest", None), ("0 min", "lactate_0min", 0),
    ("2 min", "lactate_2min", 2), ("5 min", "lactate_5min", 5),
    ("7 min", "lactate_7min", 7), ("9 min", "lactate_9min", 9),
]


def _enrich(test):
    score = compute_score(test["level"], test["shuttle"])
    distance = compute_distance(test["level"], test["shuttle"])
    vo2max = compute_vo2max(distance)
    test.update(score=score, distance=distance, vo2max=vo2max)
    return test


def render(sport, entry_type):
    athletes = db.list_athletes(sport_id=sport["id"])
    athlete_lookup = {a["name"]: a for a in athletes}
    selection = st.selectbox("Athlete", ["All athletes"] + list(athlete_lookup.keys()))

    if selection == "All athletes":
        _render_overview()
    else:
        _render_athlete(selection, athlete_lookup[selection])


# =====================================================================
# Overview - squad-wide only
# =====================================================================
def _render_overview():
    tests = [_enrich(t) for t in db.get_yoyo_tests()]
    if not tests:
        st.info("No Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test tests logged yet.")
        return

    by_athlete = {}
    for t in tests:
        by_athlete.setdefault(t["athletes"]["name"], []).append(t)
    all_names = sorted(by_athlete.keys())
    athlete_lookup_by_name = {n: by_athlete[n][0]["athletes"] for n in all_names}

    names = all_names

    latest = {n: sorted(by_athlete[n], key=lambda t: t["test_date"])[-1] for n in names}
    included_tests = [t for n in names for t in by_athlete[n]]

    report = ReportBuilder("Squash - Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test Overview", get_brand_color("Squash"))

    with st.container(border=True):
        render_metric_row([
            {"label": "Athletes Tested", "value": len(names)},
            {"label": "Tests Recorded", "value": len(included_tests)},
            {"label": "Squad Avg VO2max", "value": f"{sum(t['vo2max'] for t in latest.values())/len(latest):.1f} ml/kg/min"},
        ], COLORS)
        report.metrics([("Athletes Tested", len(names)), ("Tests Recorded", len(included_tests)),
                         ("Squad Avg VO2max", f"{sum(t['vo2max'] for t in latest.values())/len(latest):.1f} ml/kg/min")])

    with st.container(border=True):
        st.markdown("**Squad Ratings** - most recent test per athlete")
        rows_html = ""
        for n in names:
            t = latest[n]
            gender = t["athletes"].get("gender")
            rating = rate_score(t["score"], gender)
            color = RATING_COLOR.get(rating)
            rows_html += (
                f"<tr><td style='padding:8px 12px;color:var(--text);'>{n}</td>"
                f"<td style='padding:8px 12px;color:var(--muted);'>{gender or '-'}</td>"
                f"<td style='padding:8px 12px;'><span style='background:{color};color:#04121f;"
                f"padding:3px 12px;border-radius:8px;font-weight:700;'>{t['score']}</span></td>"
                f"<td style='padding:8px 12px;color:{color};font-weight:600;'>{rating or 'No gender set'}</td></tr>"
            )
        table_html = (
            f"<table style='width:100%;border-collapse:collapse;background:var(--panel);"
            f"border:1px solid var(--line);border-radius:12px;overflow:hidden;'>"
            f"<tr style='background:var(--panel-2);color:var(--muted);font-size:12px;text-align:left;'>"
            f"<th style='padding:8px 12px;'>Athlete</th><th style='padding:8px 12px;'>Gender</th>"
            f"<th style='padding:8px 12px;'>Score</th><th style='padding:8px 12px;'>Rating</th></tr>"
            f"{rows_html}</table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)
        report.table("Squad Ratings", [
            {"Athlete": n, "Gender": latest[n]["athletes"].get("gender") or "-", "Score": latest[n]["score"],
             "Rating": rate_score(latest[n]["score"], latest[n]["athletes"].get("gender")) or "No gender set"}
            for n in names
        ])

        legend_html = "".join(
            f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:16px;font-size:12.5px;color:var(--muted);'>"
            f"<span style='width:11px;height:11px;border-radius:3px;background:{RATING_COLOR[r]};display:inline-block;'></span>{r}</span>"
            for r in RATING_ORDER
        )
        st.markdown(f"<div style='margin-top:10px;'>{legend_html}</div>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**Where the Squad Sits** - distance covered, grouped by gender")
        for gender_group, group_label in [("Male", "Men"), ("Female", "Women")]:
            group_names = [n for n in names if latest[n]["athletes"].get("gender") == gender_group]
            if not group_names:
                continue
            group_names.sort(key=lambda n: latest[n]["distance"], reverse=True)
            colors = [RATING_COLOR.get(rate_score(latest[n]["score"], gender_group)) for n in group_names]
            fig = go.Figure(go.Bar(
                y=group_names, x=[latest[n]["distance"] for n in group_names], orientation="h", marker_color=colors,
                text=[f"{latest[n]['distance']:.0f} m" for n in group_names], textposition="outside",
            ))
            fig.update_layout(height=max(120, 36 * len(group_names)), margin=dict(l=0, r=40, t=25, b=0),
                               title=dict(text=group_label, font=dict(size=13)), xaxis_title="meters", **CHART_LAYOUT)
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart(f"{group_label} - Distance Covered", fig)

    with st.container(border=True):
        st.markdown("**Estimated VO2max by Athlete**")
        fig = go.Figure(go.Bar(x=names, y=[latest[n]["vo2max"] for n in names], marker_color=PLOT_COLORS["sky"]))
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="ml/kg/min", **CHART_LAYOUT)
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
        st.plotly_chart(fig, use_container_width=True)
        report.chart("Estimated VO2max by Athlete", fig)

    with st.container(border=True):
        report.render_export_controls("squash_yirc_l1_overview", key="report_yoyo_overview")

    with st.container(border=True):
        st.markdown("**Export Individual Athlete Reports**")
        st.caption("Pick one or more athletes to combine their full individual reports into a single export.")
        batch_names = st.multiselect("Select athletes", names, key="yoyo_batch_export_athletes")
        if batch_names:
            combined = ReportBuilder("Squash - Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test Individual Reports", get_brand_color("Squash"))
            for n in batch_names:
                with st.expander(n, expanded=False):
                    _render_athlete(n, athlete_lookup_by_name[n], shared_report=combined)
            with st.container(border=True):
                combined.render_export_controls("squash_yirc_l1_individuals", key="report_yoyo_batch")


# =====================================================================
# Athlete - individual, with a Date dropdown (solves "more tests later")
# =====================================================================
def _render_ladder_html(distance, gender):
    if gender not in _BAND_LOW_DIST:
        return ""
    scale_max = _LADDER_MAX[gender]
    edges = _BAND_LOW_DIST[gender]
    order = ["Very Poor", "Below Average", "Average", "Good", "Excellent", "Elite"]
    bounds = [edges[b] for b in order] + [scale_max]
    segs = ""
    for i, label in enumerate(order):
        left_pct = bounds[i] / scale_max * 100
        width_pct = (bounds[i + 1] - bounds[i]) / scale_max * 100
        segs += f"<div style='position:absolute;left:{left_pct}%;width:{max(width_pct,0.5)}%;height:100%;background:{RATING_COLOR[label]};'></div>"
    marker_pct = min(max(distance / scale_max * 100, 0), 100)
    marker = (
        f"<div style='position:absolute;left:{marker_pct}%;top:-10px;transform:translateX(-50%);"
        f"width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;"
        f"border-top:10px solid var(--text);'></div>"
    )
    labels = "".join(
        f"<span style='position:absolute;left:{bounds[i]/scale_max*100}%;font-size:10px;color:var(--muted);transform:translateX(-4px);'>{b}</span>"
        for i, b in enumerate(order)
    )
    return (
        f"<div style='position:relative;height:22px;border-radius:8px;overflow:hidden;margin-top:14px;'>{segs}{marker}</div>"
        f"<div style='position:relative;height:16px;margin-top:2px;'>{labels}</div>"
    )


def _render_athlete(name, athlete, shared_report=None):
    gender = athlete.get("gender")
    if not gender:
        st.warning(f"{name} doesn't have a gender set yet, so results can't be rated. Fix this in Admin.")

    tests = sorted([_enrich(t) for t in db.get_yoyo_tests(athlete_id=athlete["id"])], key=lambda t: t["test_date"])
    if not tests:
        st.info(f"No Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test tests logged yet for {name}.")
        return

    date_labels = [f"{t['test_date']}" + (f" - {t['stage']}" if t.get("stage") else "") for t in tests]
    chosen_idx = st.selectbox("Test date", range(len(date_labels)), format_func=lambda i: date_labels[i], index=len(date_labels) - 1, key=f"yoyo_date_select_{name}")
    current = tests[chosen_idx]

    age_text = f", {current['age']} yrs" if current.get("age") else ""
    st.subheader(f"{name}" + (f" - {gender}{age_text}" if gender else ""))

    compare = None
    if len(tests) > 1:
        other_indices = [i for i in range(len(tests)) if i != chosen_idx]
        default_idx = other_indices.index(chosen_idx - 1) if (chosen_idx - 1) in other_indices else 0
        compare_idx = st.selectbox(
            "Compare with", other_indices, format_func=lambda i: date_labels[i], index=default_idx, key=f"yoyo_compare_{name}",
        )
        compare = tests[compare_idx]

    rating = rate_score(current["score"], gender)
    rating_color = RATING_COLOR.get(rating)

    own_report = shared_report is None
    report = shared_report if shared_report is not None else ReportBuilder(f"Squash - Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test - {name}", get_brand_color("Squash"))
    if shared_report is not None:
        report.heading(name)

    with st.container(border=True):
        col_ladder, col_norms = st.columns([1.4, 1], gap="large")
        with col_ladder:
            st.markdown(
                f"<span style='background:{rating_color};color:#04121f;padding:4px 14px;border-radius:8px;"
                f"font-weight:700;font-size:15px;'>{rating or 'No gender set'}</span>",
                unsafe_allow_html=True,
            )
            report.insight(f"{name}'s rating on {current['test_date']} was {rating or 'not available (no gender set)'}.")
            if gender:
                st.markdown(_render_ladder_html(current["distance"], gender), unsafe_allow_html=True)
        with col_norms:
            st.markdown("**Normative Bands**")
            band_rows = ""
            for label in RATING_ORDER:
                is_current = (label == rating)
                row_style = "outline:2px solid var(--brand);" if is_current else ""
                band_rows += (
                    f"<tr style='{row_style}'>"
                    f"<td style='padding:5px 8px;'><span style='background:{RATING_COLOR[label]};color:#04121f;"
                    f"padding:2px 8px;border-radius:8px;font-weight:700;font-size:11.5px;'>{label}</span></td>"
                    f"<td style='padding:5px 8px;color:var(--text);font-size:12px;'>{_BAND_TEXT['Male'][label]}</td>"
                    f"<td style='padding:5px 8px;color:var(--text);font-size:12px;'>{_BAND_TEXT['Female'][label]}</td></tr>"
                )
            band_table_html = (
                f"<table style='width:100%;border-collapse:collapse;'>"
                f"<tr style='color:var(--muted);font-size:10.5px;text-align:left;'>"
                f"<th style='padding:5px 8px;'>Tier</th><th style='padding:5px 8px;'>Male</th>"
                f"<th style='padding:5px 8px;'>Female</th></tr>{band_rows}</table>"
            )
            st.markdown(band_table_html, unsafe_allow_html=True)
            report.table("Normative Bands", [
                {"Tier": label, "Male": _BAND_TEXT["Male"][label], "Female": _BAND_TEXT["Female"][label]}
                for label in RATING_ORDER
            ])

    with st.container(border=True):
        hr_max = estimate_hr_max(current.get("age"))
        peak_hr = current.get("peak_hr")
        hr_pct = f" ({peak_hr/hr_max*100:.0f}% of est. max)" if peak_hr and hr_max else ""
        render_metric_row([
            {"label": "Level.Shuttle", "value": f"{current['level']}.{current['shuttle']}"},
            {"label": "Distance Covered", "value": f"{current['distance']:.0f} m"},
            {"label": "Est. VO2max", "value": f"{current['vo2max']:.1f} ml/kg/min"},
            {"label": "Peak HR", "value": f"{peak_hr} bpm{hr_pct}" if peak_hr else "-"},
        ], COLORS)
        report.metrics([
            ("Level.Shuttle", f"{current['level']}.{current['shuttle']} ({rating or 'No gender set'})"),
            ("Distance Covered", f"{current['distance']:.0f} m"), ("Est. VO2max", f"{current['vo2max']:.1f} ml/kg/min"),
            ("Peak HR", f"{peak_hr} bpm{hr_pct}" if peak_hr else "-"),
        ])

        if compare:
            d_vo2 = current["vo2max"] - compare["vo2max"]
            d_dist = current["distance"] - compare["distance"]
            st.markdown("**Change Since Compared Test**")
            render_metric_row([
                {"label": "VO2max", "value": f"{current['vo2max']:.1f} ml/kg/min", "delta": f"{'↓' if d_vo2 < 0 else '↑'} {abs(d_vo2):.1f}", "status": "good" if d_vo2 > 0 else "bad" if d_vo2 < 0 else None},
                {"label": "Distance", "value": f"{current['distance']:.0f} m", "delta": f"{'↓' if d_dist < 0 else '↑'} {abs(d_dist):.0f} m", "status": "good" if d_dist > 0 else "bad" if d_dist < 0 else None},
            ], COLORS)
            report.insight(
                f"Compared with the test on {compare['test_date']}, {name}'s VO2max changed by {d_vo2:+.1f} ml/kg/min "
                f"and distance covered changed by {d_dist:+.0f} m."
            )

    # ---------- Lactate: peak shown separately from the time-based curve ----------
    curve_values = [current.get(key) for _, key, _ in RECOVERY_CURVE_POINTS]
    peak_lac = current.get("lactate_peak")
    if any(v is not None for v in curve_values) or peak_lac is not None:
        with st.container(border=True):
            st.markdown("**Blood Lactate** - peak effort and post-test recovery")
            pc1, pc2 = st.columns([1, 3], gap="large")
            with pc1:
                render_metric_row([{"label": "Peak Lactate", "value": f"{peak_lac} mmol/L" if peak_lac is not None else "-",
                                     "caption": "Shown separately - peak can occur at any point during the test, not at a fixed time."}], COLORS)
            with pc2:
                if any(v is not None for v in curve_values):
                    fig = go.Figure(go.Scatter(
                        x=[label for label, _, _ in RECOVERY_CURVE_POINTS], y=curve_values,
                        mode="lines+markers", line=dict(color=PLOT_COLORS["lose"]),
                    ))
                    fig.update_layout(height=240, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="mmol/L", **CHART_LAYOUT)
                    fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
                    st.plotly_chart(fig, use_container_width=True)
                    report.chart("Blood Lactate Recovery Curve", fig)
                else:
                    st.info("No post-test recovery samples recorded yet.")

    with st.container(border=True):
        if own_report:
            report.render_export_controls(f"squash_yirc_l1_{name.replace(' ', '_')}", key="report_yoyo_athlete")