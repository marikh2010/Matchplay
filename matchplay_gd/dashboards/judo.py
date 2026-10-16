import streamlit as st
import plotly.graph_objects as go
import db
from judo_logic import summarize, stronger_side, entry_checks, ratio_scaled, GRIP_RATING_ORDER
from style import COLORS, PLOT_COLORS, CHART_LAYOUT, get_brand_color, render_metric_row
from report_export import ReportBuilder

SPORT = "Judo"
ET_LABEL = "Judo Fitness Test"
# Resolved at render time (not import time) so charts follow the active
# light/dark palette that apply_style() loads into COLORS.
def _side_color():
    return {"Right": PLOT_COLORS["blue"], "Left": PLOT_COLORS["blue_light"]}


def _scale_color():
    return {"abs": PLOT_COLORS["blue"], "ratio": PLOT_COLORS["blue_light"], "allo": PLOT_COLORS["sky"]}

GRIP_RATING_COLOR = {
    "Excellent": "#60B77A", "Good": "#A4BE55", "Regular": "#D9B84E",
    "Poor": "#D99352", "Very Poor": "#CF7474", None: "#8A98AA",
}
RAMP_NOTE = "Peak power and predicted VO2max use the Judo Fitness Test sheet formulas."


def _fmt(v, spec, unit=""):
    return f"{v:{spec}}{unit}" if v is not None else "-"


def _enriched(athlete_id=None):
    tests = db.get_judo_tests_with_trials(athlete_id=athlete_id)
    for t in tests:
        t["m"] = summarize(t)
    return tests


def _rating_chip(label):
    if not label:
        return "-"
    return (f"<span style='background:{GRIP_RATING_COLOR[label]};color:#04121f;padding:2px 10px;"
            f"border-radius:8px;font-weight:700;font-size:12px;'>{label}</span>")


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
def _hbar(names, values, unit, color, spec):
    fig = go.Figure(go.Bar(
        y=names, x=values, orientation="h", marker_color=color,
        text=[_fmt(v, spec) for v in values], textposition="outside",
    ))
    top = max((v for v in values if v is not None), default=0)
    fig.update_traces(cliponaxis=False)
    fig.update_layout(height=max(170, 46 * len(names)), margin=dict(l=0, r=20, t=10, b=0),
                      xaxis=dict(title=unit, range=[0, top * 1.3 if top else 1]), **CHART_LAYOUT)
    fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
    return fig


def _render_overview():
    tests = _enriched()
    if not tests:
        st.info(f"No {ET_LABEL} results logged yet.")
        return

    by_athlete = {}
    for t in tests:
        by_athlete.setdefault(t["athletes"]["name"], []).append(t)
    names = sorted(by_athlete.keys())
    athlete_lookup_by_name = {n: by_athlete[n][0]["athletes"] for n in names}
    latest = {n: sorted(by_athlete[n], key=lambda t: t["test_date"])[-1]["m"] for n in names}
    no_gender = [n for n in names if not latest[n]["gender"]]

    report = ReportBuilder(f"{SPORT} - {ET_LABEL} Overview", get_brand_color(SPORT))

    with st.container(border=True):
        masses = [latest[n]["body_mass"] for n in names if latest[n]["body_mass"]]
        items = [
            {"label": "Athletes Tested", "value": len(names)},
            {"label": "Tests Recorded", "value": len(tests)},
            {"label": "Body Mass Range", "value": f"{min(masses):.1f}-{max(masses):.1f} kg" if masses else "-"},
            {"label": "Retested Athletes", "value": sum(1 for n in names if len(by_athlete[n]) > 1)},
        ]
        render_metric_row(items, COLORS)
        report.metrics([(i["label"], i["value"]) for i in items])
        if no_gender:
            st.info(f"No sex set for: {', '.join(no_gender)}. Handgrip ratings use male judo norms, so they only show once sex is set in Admin.")

    # ---------- IMTP three ways ----------
    with st.container(border=True):
        st.markdown("**IMTP Peak Force - three ways of accounting for body size**")
        ranked = [n for n in names if latest[n]["imtp_best"] is not None]
        if ranked:
            cols = st.columns(3, gap="large")
            for col, key, title, unit, spec, color in [
                (cols[0], "imtp_best", "Absolute", "N", ",.0f", _scale_color()["abs"]),
                (cols[1], "imtp_rel", "Relative (N/kg)", "N/kg", ".2f", _scale_color()["ratio"]),
                (cols[2], "imtp_allo", "Allometric", "N/kg^0.67", ".1f", _scale_color()["allo"]),
            ]:
                with col:
                    order = sorted(ranked, key=lambda n: latest[n][key])
                    fig = _hbar(order, [latest[n][key] for n in order], unit, color, spec)
                    st.plotly_chart(fig, use_container_width=True)
                    report.chart(f"IMTP Peak Force - {title}", fig)
        else:
            st.info("No IMTP results yet.")

    # ---------- Handgrip ----------
    with st.container(border=True):
        st.markdown("**Handgrip Peak Force** - best trial per hand, with judo reference rating")
        rows_html, report_rows = "", []
        for n in names:
            m = latest[n]
            male = m["gender"] == "Male"
            asym_txt = _fmt(m["grip_asym"], ".1f", "%")
            if m["grip_asym_flag"]:
                asym_txt = (f"<span style='background:{COLORS['amber']};color:#04121f;padding:2px 10px;border-radius:8px;"
                            f"font-weight:700;'>{asym_txt}</span>")
            rows_html += (
                f"<tr><td style='padding:8px 12px;font-weight:600;'>{n}</td>"
                f"<td style='padding:8px 12px;'>{_fmt(m['grip_best_right'], ',.0f', ' N')} <span style='color:var(--muted);'>({_fmt(m['grip_best_right_kgf'], '.1f', ' kgf')})</span></td>"
                f"<td style='padding:8px 12px;'>{_rating_chip(m['grip_rating_right']) if male else 'n/a'}</td>"
                f"<td style='padding:8px 12px;'>{_fmt(m['grip_best_left'], ',.0f', ' N')} <span style='color:var(--muted);'>({_fmt(m['grip_best_left_kgf'], '.1f', ' kgf')})</span></td>"
                f"<td style='padding:8px 12px;'>{_rating_chip(m['grip_rating_left']) if male else 'n/a'}</td>"
                f"<td style='padding:8px 12px;'>{_fmt(m['grip_allo'], '.1f')}</td>"
                f"<td style='padding:8px 12px;'>{asym_txt} <span style='color:var(--muted);font-size:11px;'>CV {_fmt(m['grip_cv'], '.1f', '%')}</span></td></tr>"
            )
            report_rows.append({
                "Athlete": n, "Right (N)": _fmt(m["grip_best_right"], ",.0f"), "Right rating": m["grip_rating_right"] or "n/a",
                "Left (N)": _fmt(m["grip_best_left"], ",.0f"), "Left rating": m["grip_rating_left"] or "n/a",
                "Allometric (N/kg^0.67)": _fmt(m["grip_allo"], ".1f"), "Asymmetry": _fmt(m["grip_asym"], ".1f", "%"),
                "Trial CV": _fmt(m["grip_cv"], ".1f", "%"),
            })
        heads = ["Athlete", "Right", "Rating R", "Left", "Rating L", "Allometric (N/kg^0.67)", "Asymmetry"]
        st.markdown(
            f"<div style='overflow-x:auto;'><table style='width:100%;border-collapse:collapse;background:var(--panel);"
            f"border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13px;color:var(--text);'>"
            f"<tr style='background:var(--panel-2);color:var(--muted);font-size:12px;text-align:left;'>"
            + "".join(f"<th style='padding:8px 12px;'>{h}</th>" for h in heads) + f"</tr>{rows_html}</table></div>",
            unsafe_allow_html=True,
        )
        legend = "".join(
            f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:12px;color:var(--muted);'>"
            f"<span style='width:11px;height:11px;border-radius:3px;background:{GRIP_RATING_COLOR[r]};display:inline-block;'></span>{r}</span>"
            for r in GRIP_RATING_ORDER
        )
        st.markdown(f"<div style='margin-top:10px;'>{legend}</div>", unsafe_allow_html=True)
        report.table("Handgrip Peak Force", report_rows)

    # ---------- Ramp ----------
    with st.container(border=True):
        st.markdown("**1-min Ramp Test** - peak power and predicted VO2max")
        ranked = [n for n in names if latest[n]["peak_power"] is not None]
        if ranked:
            col1, col2 = st.columns(2, gap="large")
            for col, key, title, unit, color, spec in [
                (col1, "peak_power", "Peak power", "W", PLOT_COLORS["blue"], ".0f"),
                (col2, "vo2max", "Predicted VO2max", "mL/kg/min", PLOT_COLORS["sky"], ".1f"),
            ]:
                with col:
                    vals = [n for n in ranked if latest[n][key] is not None]
                    order = sorted(vals, key=lambda n: latest[n][key])
                    fig = _hbar(order, [latest[n][key] for n in order], unit, color, spec)
                    st.plotly_chart(fig, use_container_width=True)
                    report.chart(title, fig)
        else:
            st.info("No ramp test results yet.")

    # ---------- Squad matrix ----------
    with st.container(border=True):
        st.markdown("**Squad Test Matrix** - most recent test per athlete")
        rows = [{
            "Athlete": n, "Sex": latest[n]["gender"] or "-", "Body mass": _fmt(latest[n]["body_mass"], ".2f", " kg"),
            "IMTP": _fmt(latest[n]["imtp_best"], ",.0f", " N"), "IMTP /kg": _fmt(latest[n]["imtp_rel"], ".2f"),
            "IMTP /kg^0.67": _fmt(latest[n]["imtp_allo"], ".1f"),
            "Max RFD R/L": f"{_fmt(latest[n]['rfd_best_right'], ',.0f')} / {_fmt(latest[n]['rfd_best_left'], ',.0f')}",
            "Peak power": _fmt(latest[n]["peak_power"], ".0f", " W"), "W/kg": _fmt(latest[n]["power_per_kg"], ".2f"),
            "Pred. VO2max": _fmt(latest[n]["vo2max"], ".1f", " mL/kg/min"),
            "Peak HR": _fmt(latest[n]["peak_hr"], "d", " bpm"),
        } for n in names]
        st.table(rows)
        report.table("Squad Test Matrix", rows)

    # ---------- Change over time ----------
    retested = [n for n in names if len(by_athlete[n]) > 1]
    if retested:
        with st.container(border=True):
            st.markdown("**Change Over Time** - athletes with 2+ tests")
            options = {"IMTP allometric (N/kg^0.67)": "imtp_allo", "IMTP absolute (N)": "imtp_best",
                       "IMTP relative (N/kg)": "imtp_rel", "Peak power (W)": "peak_power", "Predicted VO2max (mL/kg/min)": "vo2max"}
            metric = st.radio("Metric", list(options.keys()), horizontal=True, key="judo_trend_metric")
            key = options[metric]
            palette = [PLOT_COLORS["blue"], PLOT_COLORS["sky"], PLOT_COLORS["win"], PLOT_COLORS["amber"], PLOT_COLORS["blue_light"], PLOT_COLORS["lose"]]
            fig = go.Figure()
            for i, n in enumerate(retested):
                ts = sorted(by_athlete[n], key=lambda t: t["test_date"])
                fig.add_scatter(x=[t["test_date"] for t in ts], y=[t["m"][key] for t in ts], name=n, mode="lines+markers",
                                line=dict(color=palette[i % len(palette)]))
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title=metric, **CHART_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)
            report.chart(f"Change Over Time - {metric}", fig)

    with st.container(border=True):
        report.render_export_controls("judo_fitness_overview", key="report_judo_overview")

    with st.container(border=True):
        st.markdown("**Export Individual Athlete Reports**")
        batch_names = st.multiselect("Select athletes", names, key="judo_batch_export_athletes")
        if batch_names:
            combined = ReportBuilder(f"{SPORT} - {ET_LABEL} Individual Reports", get_brand_color(SPORT))
            for n in batch_names:
                with st.expander(n, expanded=False):
                    _render_athlete(n, athlete_lookup_by_name[n], shared_report=combined)
            with st.container(border=True):
                combined.render_export_controls("judo_fitness_individuals", key="report_judo_batch")


# =====================================================================
# Athlete - individual, with Test date + Compare with dropdowns
# =====================================================================
def _trial_bars(trials, key_r, key_l, unit, title):
    x = [f"Trial {t['trial_no']}" for t in trials]
    fig = go.Figure()
    for side, key in [("Right", key_r), ("Left", key_l)]:
        vals = [t.get(key) for t in trials]
        fig.add_bar(name=side, x=x, y=vals, marker_color=_side_color()[side],
                    text=[f"{v:,.0f}" if v is not None else "" for v in vals], textposition="outside")
    fig.update_layout(barmode="group", height=280, margin=dict(l=0, r=0, t=30, b=0), yaxis_title=unit,
                      title=dict(text=title, font=dict(size=13)), legend=dict(orientation="h", y=-0.15), **CHART_LAYOUT)
    fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
    return fig


def _rank_text(value, pool, higher_better=True):
    vals = sorted([v for v in pool if v is not None], reverse=higher_better)
    if value is None or len(vals) < 2:
        return ""
    return f" ({vals.index(value) + 1} of {len(vals)} in squad)"


def _render_athlete(name, athlete, shared_report=None):
    tests = sorted(_enriched(athlete_id=athlete["id"]), key=lambda t: t["test_date"])
    if not tests:
        st.info(f"No {ET_LABEL} results logged yet for {name}.")
        return

    gender = athlete.get("gender")
    st.subheader(name + (f" - {gender}" if gender else ""))
    if not gender:
        st.info(f"{name} has no sex set. Handgrip ratings use male judo norms, so they only show once sex is set in Admin.")

    date_labels = [f"{t['test_date']}" + (f" - {t['stage']}" if t.get("stage") else "") for t in tests]
    chosen_idx = st.selectbox("Test date", range(len(date_labels)), format_func=lambda i: date_labels[i],
                              index=len(date_labels) - 1, key=f"judo_date_select_{name}")
    current = tests[chosen_idx]
    m = current["m"]
    trials = sorted(current.get("trials") or [], key=lambda t: t["trial_no"])

    compare = None
    if len(tests) > 1:
        other = [i for i in range(len(tests)) if i != chosen_idx]
        default_idx = other.index(chosen_idx - 1) if (chosen_idx - 1) in other else 0
        compare_idx = st.selectbox("Compare with", other, format_func=lambda i: date_labels[i], index=default_idx, key=f"judo_compare_{name}")
        compare = tests[compare_idx]

    own_report = shared_report is None
    report = shared_report if shared_report is not None else ReportBuilder(f"{SPORT} - {ET_LABEL} - {name}", get_brand_color(SPORT))
    if shared_report is not None:
        report.heading(name)

    # ---------- Headline metrics ----------
    with st.container(border=True):
        row1 = [
            {"label": "Body Mass", "value": _fmt(m["body_mass"], ".2f", " kg")},
            {"label": "IMTP Relative Force", "value": _fmt(m["imtp_rel"], ".2f", " N/kg"),
             "caption": f"{_fmt(m['imtp_best'], ',.0f', ' N')} · {_fmt(m['imtp_allo'], '.1f', ' N/kg^0.67')}"},
            {"label": "Ramp Peak Power", "value": _fmt(m["peak_power"], ".0f", " W"), "caption": _fmt(m["power_per_kg"], ".2f", " W/kg")},
            {"label": "Predicted VO2max", "value": _fmt(m["vo2max"], ".1f", " mL/kg/min"),
             "caption": f"Peak HR {_fmt(m['peak_hr'], 'd', ' bpm')}"},
        ]
        render_metric_row(row1, COLORS)
        row2 = [
            {"label": "Grip - Right", "value": _fmt(m["grip_best_right"], ",.0f", " N"),
             "caption": f"{_fmt(m['grip_best_right_kgf'], '.1f', ' kgf')} · {m['grip_rating_right'] or 'no rating'}"},
            {"label": "Grip - Left", "value": _fmt(m["grip_best_left"], ",.0f", " N"),
             "caption": f"{_fmt(m['grip_best_left_kgf'], '.1f', ' kgf')} · {m['grip_rating_left'] or 'no rating'}"},
            {"label": "Grip Asymmetry", "value": _fmt(m["grip_asym"], ".1f", "%"), "caption": f"trial CV {_fmt(m['grip_cv'], '.1f', '%')}",
             "status": "warning" if m["grip_asym_flag"] else None},
            {"label": "Max RFD Asymmetry", "value": _fmt(m["rfd_asym"], ".1f", "%"), "caption": f"trial CV {_fmt(m['rfd_cv'], '.1f', '%')}",
             "status": "warning" if m["rfd_asym_flag"] else None},
        ]
        render_metric_row(row2, COLORS)
        report.metrics([(i["label"], f"{i['value']} ({i['caption']})" if i.get("caption") else i["value"]) for i in row1 + row2])

        if compare:
            cm = compare["m"]
            st.markdown(f"**Change Since {compare['test_date']}**")
            deltas = []
            for label, key, spec, unit in [
                ("IMTP Relative", "imtp_rel", ".2f", " N/kg"), ("IMTP Peak", "imtp_best", ",.0f", " N"),
                ("Predicted VO2max", "vo2max", ".1f", ""), ("Body Mass", "body_mass", ".2f", " kg"),
            ]:
                a, b = m[key], cm[key]
                if a is None or b is None:
                    deltas.append({"label": label, "value": _fmt(a, spec, unit)})
                    continue
                d = a - b
                deltas.append({"label": label, "value": _fmt(a, spec, unit),
                               "delta": "no change" if d == 0 else f"{'↓' if d < 0 else '↑'} {abs(d):{spec}}"})
            render_metric_row(deltas, COLORS)
            report.metrics([(f"{d['label']} (change)", f"{d['value']} {d.get('delta', '')}".strip()) for d in deltas])

    # ---------- Handgrip ----------
    if trials:
        with st.container(border=True):
            st.markdown("**Handgrip Dynamometer** - right vs left, by trial")
            col1, col2 = st.columns(2, gap="large")
            with col1:
                fig = _trial_bars(trials, "grip_right", "grip_left", "N", "Peak Force")
                st.plotly_chart(fig, use_container_width=True)
                report.chart("Handgrip Peak Force by Trial", fig)
            with col2:
                fig = _trial_bars(trials, "max_rfd_right", "max_rfd_left", "N/s", "Max RFD")
                st.plotly_chart(fig, use_container_width=True)
                report.chart("Handgrip Max RFD by Trial", fig)
        # ---------- IMTP ----------
        imtp = [(t["trial_no"], t.get("imtp_peak")) for t in trials if t.get("imtp_peak") is not None]
        if imtp:
            with st.container(border=True):
                st.markdown("**Isometric Mid-Thigh Pull** - gross peak force by trial")
                best = max(v for _, v in imtp)
                fig = go.Figure(go.Bar(
                    x=[f"Trial {n}" for n, _ in imtp], y=[v for _, v in imtp],
                    marker_color=[PLOT_COLORS["blue"] if v == best else PLOT_COLORS["blue_light"] for _, v in imtp],
                    text=[f"{v:,.0f} N" for _, v in imtp], textposition="outside",
                ))
                fig.update_layout(height=260, margin=dict(l=0, r=0, t=25, b=0), yaxis_title="N", **CHART_LAYOUT)
                fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
                st.plotly_chart(fig, use_container_width=True)
                report.chart("IMTP Peak Force by Trial", fig)

    # ---------- Over time ----------
    if len(tests) > 1:
        with st.container(border=True):
            st.markdown("**Over Time** - every recorded test")
            col1, col2 = st.columns(2, gap="large")
            dates = [str(t["test_date"]) for t in tests]
            for col, key, title, unit, color in [
                (col1, "imtp_rel", "IMTP Relative Force", "N/kg", PLOT_COLORS["blue"]),
                (col2, "vo2max", "Predicted VO2max", "mL/kg/min", PLOT_COLORS["sky"]),
            ]:
                with col:
                    fig = go.Figure(go.Scatter(x=dates, y=[t["m"][key] for t in tests], mode="lines+markers",
                                               line=dict(color=color), marker=dict(size=9)))
                    fig.update_layout(height=240, margin=dict(l=0, r=0, t=30, b=0), yaxis_title=unit,
                                      title=dict(text=title, font=dict(size=13)), **CHART_LAYOUT)
                    st.plotly_chart(fig, use_container_width=True)
                    report.chart(f"{title} Over Time", fig)

    # ---------- Raw trials ----------
    with st.container(border=True):
        with st.expander("All Trials (This Test)"):
            table = [{
                "Trial": t["trial_no"], "Grip R": t.get("grip_right"), "Grip L": t.get("grip_left"),
                "Max RFD R": t.get("max_rfd_right"), "Max RFD L": t.get("max_rfd_left"),
                "Avg RFD R": t.get("avg_rfd_right"), "Avg RFD L": t.get("avg_rfd_left"), "IMTP (N)": t.get("imtp_peak"),
                "IMTP (N/kg)": ratio_scaled(t.get("imtp_peak"), m["body_mass"]),
            } for t in trials]
            st.table(table)
        report.table("All Trials", [{k: ("-" if v is None else v) for k, v in r.items()} for r in table])

        if own_report:
            report.render_export_controls(f"judo_fitness_{name.replace(' ', '_')}", key="report_judo_athlete")
