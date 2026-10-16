import datetime
import streamlit as st
import plotly.graph_objects as go
import db
from longjump_logic import compute_attempt_velocities, compute_total_time, is_still_accelerating
from style import COLORS, PLOT_COLORS, get_brand_color, CHART_LAYOUT, render_metric_row
from report_export import ReportBuilder

VALIDITY_SYMBOL = {"Valid": "circle", "Invalid": "x", "N/A": "circle-open"}
VALIDITY_COLOR = {"Valid": PLOT_COLORS["win"], "Invalid": PLOT_COLORS["lose"], "N/A": PLOT_COLORS["muted"]}


def _enrich(attempt):
    v = compute_attempt_velocities(attempt["first_10m"], attempt["split_10_15"], attempt["split_15_20"])
    attempt.update(v)
    attempt["total_time"] = compute_total_time(attempt["first_10m"], attempt["split_10_15"], attempt["split_15_20"])
    attempt["still_accelerating"] = is_still_accelerating(v["v_10_15"], v["v_15_20"])
    return attempt


def _render_date_filter(dates, key):
    """Same 'Filter' popover as the Matchplay dashboard, date-only: pick a
    recorded date, optionally an end date for a range. Returns (start, end)
    as 'YYYY-MM-DD' strings, or None when no date is chosen (show all)."""
    available_dates = sorted({datetime.date.fromisoformat(str(d)[:10]) for d in dates})
    with st.popover("Filter", use_container_width=True):
        start_date = st.selectbox(
            "From (recorded dates)",
            [None, *available_dates],
            format_func=lambda value: "All dates" if value is None else value.strftime("%d/%m/%Y"),
            key=f"{key}_from",
        )
        if start_date is None:
            st.caption("Choose one date or add an end date for a range.")
            return None
        end_date = st.selectbox(
            "To (optional)",
            [None, *[d for d in available_dates if d >= start_date]],
            format_func=lambda value: "Same day" if value is None else value.strftime("%d/%m/%Y"),
            key=f"{key}_to",
        ) or start_date
    return str(start_date), str(end_date)


def _in_range(date, date_range):
    return date_range is None or date_range[0] <= str(date)[:10] <= date_range[1]


def _range_label(date_range):
    if date_range is None:
        return "All dates"
    fmt = lambda d: datetime.date.fromisoformat(d).strftime("%d/%m/%Y")
    start, end = date_range
    return fmt(start) if start == end else f"{fmt(start)} to {fmt(end)}"


def _time_change_pct(rows, field):
    """% change in a segment's time (field, e.g. 'split_15_20') vs. the
    previous shown jump in the same session - lower is better. Returns
    (pct, compared_jump_label) per row; the first jump of each session has
    nothing to compare to and gets (None, None)."""
    out, prev = [], {}
    for r in rows:
        t = r.get(field)
        last = prev.get(r["date"])
        if t and last:
            out.append((round((t - last[0]) / last[0] * 100, 1), last[1]))
        else:
            out.append((None, None))
        if t:
            prev[r["date"]] = (t, r["jump_label"])
    return out


def render(sport, entry_type):
    athletes = db.list_athletes(sport_id=sport["id"])
    athlete_lookup = {a["name"]: a for a in athletes}
    athlete_col, _, filter_col = st.columns([1.5, 1, 0.8], gap="small")
    with athlete_col:
        selection = st.selectbox("Athlete", ["All athletes"] + list(athlete_lookup.keys()))

    athlete = athlete_lookup.get(selection)
    tests = db.get_longjump_tests_with_attempts(athlete_id=athlete["id"] if athlete else None)
    if not tests:
        st.info("No Long Jump tests logged yet." if athlete is None else f"No Long Jump tests logged yet for {selection}.")
        return
    with filter_col:
        date_range = _render_date_filter([t["test_date"] for t in tests], key=f"lj_filter_{athlete['id'] if athlete else 'all'}")

    if athlete is None:
        _render_overview(tests, date_range)
    else:
        _render_athlete(selection, athlete, tests=tests, date_range=date_range)


def _render_overview(tests, date_range=None):
    tests = [t for t in tests if _in_range(t["test_date"], date_range)]
    if not tests:
        st.info("No Long Jump tests in the selected dates.")
        return

    by_athlete = {}
    all_attempts = 0
    valid_attempts = 0
    for t in tests:
        for a in t["attempts"]:
            a = _enrich(a)
            a["test_date"] = t["test_date"]
            all_attempts += 1
            if a.get("validity") == "Valid":
                valid_attempts += 1
            by_athlete.setdefault(t["athletes"]["name"], []).append(a)

    all_names = sorted(by_athlete.keys())
    if not all_names:
        st.info("No attempts logged yet.")
        return
    athlete_lookup_by_name = {t["athletes"]["name"]: t["athletes"] for t in tests}

    names = all_names

    valid_by_name = {n: [a for a in by_athlete[n] if a.get("validity") == "Valid"] for n in names}
    best_v = {n: max((a["v_15_20"] for a in valid_by_name[n] if a["v_15_20"]), default=None) for n in names}
    best_jump = {n: max((a["jump_length"] for a in valid_by_name[n] if a.get("jump_length")), default=None) for n in names}
    included_attempts = sum(len(by_athlete[n]) for n in names)
    included_valid = sum(len(valid_by_name[n]) for n in names)

    report = ReportBuilder("Long Jump - Overview", get_brand_color("Long Jump"))

    with st.container(border=True):
        squad_best = max((v for v in best_v.values() if v), default=None)
        render_metric_row([
            {"label": "Athletes Tracked", "value": len(names)},
            {"label": "Sessions Recorded", "value": len(tests)},
            {"label": "Valid Attempt Rate", "value": f"{included_valid}/{included_attempts} ({included_valid/included_attempts*100:.0f}%)" if included_attempts else "-"},
            {"label": "Best 15-20m Velocity", "value": f"{squad_best:.2f} m/s" if squad_best else "-"},
        ], COLORS)
        report.metrics([
            ("Athletes Tracked", len(names)), ("Sessions Recorded", len(tests)),
            ("Valid Attempt Rate", f"{included_valid}/{included_attempts} ({included_valid/included_attempts*100:.0f}%)" if included_attempts else "-"),
            ("Best 15-20m Velocity", f"{squad_best:.2f} m/s" if squad_best else "-"),
        ])

    with st.container(border=True):
        pairs = [(n, best_v[n], best_jump[n]) for n in names if best_v[n] and best_jump[n]]
        if pairs:
            st.markdown("**Approach Velocity vs. Jump Distance** - squad scatter, each point is one athlete's best pairing")
            fig = go.Figure(go.Scatter(
                x=[p[1] for p in pairs], y=[p[2] for p in pairs], mode="markers+text",
                text=[p[0] for p in pairs], textposition="top center",
                marker=dict(size=12, color=PLOT_COLORS["sky"]),
            ))
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=20, b=0),
                               xaxis_title="15-20m velocity (m/s)", yaxis_title="Jump distance (m)", **CHART_LAYOUT)
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart("Approach Velocity vs. Jump Distance", fig)
        else:
            st.info("Need at least one athlete with both a velocity and a recorded jump length on a valid attempt to show the speed-vs-distance scatter.")

    with st.container(border=True):
        st.markdown("**Mean Split Time by Athlete**")
        fig = go.Figure()
        fig.add_bar(name="0-10m", x=names, y=[sum(a["first_10m"] for a in valid_by_name[n]) / len(valid_by_name[n]) if valid_by_name[n] else 0 for n in names], marker_color=PLOT_COLORS["amber"])
        fig.add_bar(name="10-15m", x=names, y=[sum(a["split_10_15"] for a in valid_by_name[n]) / len(valid_by_name[n]) if valid_by_name[n] else 0 for n in names], marker_color=PLOT_COLORS["sky"])
        fig.add_bar(name="15-20m", x=names, y=[sum(a["split_15_20"] for a in valid_by_name[n]) / len(valid_by_name[n]) if valid_by_name[n] else 0 for n in names], marker_color=PLOT_COLORS["win"])
        fig.update_layout(barmode="group", height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="seconds", **CHART_LAYOUT)
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
        st.plotly_chart(fig, use_container_width=True)
        report.chart("Mean Split Time by Athlete", fig)

    with st.container(border=True):
        report.render_export_controls("longjump_overview", key="report_lj_overview")

    with st.container(border=True):
        st.markdown("**Export Individual Athlete Reports**")
        st.caption("Pick one or more athletes to combine their full individual reports into a single export.")
        batch_names = st.multiselect("Select athletes", names, key="lj_batch_export_athletes")
        if batch_names:
            combined = ReportBuilder("Long Jump - Individual Reports", get_brand_color("Long Jump"))
            for n in batch_names:
                with st.expander(n, expanded=False):
                    _render_athlete(n, athlete_lookup_by_name[n], shared_report=combined, date_range=date_range)
            with st.container(border=True):
                combined.render_export_controls("longjump_individuals", key="report_lj_batch")


def _render_athlete(name, athlete, shared_report=None, tests=None, date_range=None):
    if tests is None:
        tests = db.get_longjump_tests_with_attempts(athlete_id=athlete["id"])
    tests = sorted(tests, key=lambda t: t["test_date"])
    if not tests:
        st.info(f"No Long Jump tests logged yet for {name}.")
        return

    rows = []
    for t in tests:
        for a in t["attempts"]:
            a = _enrich(a)
            rows.append({"date": str(t["test_date"]), "jump_label": f"J{a['jump_no']}", **a})

    all_valid_rows = [r for r in rows if r.get("validity") == "Valid"]

    st.subheader(name)
    show = st.radio("Show Attempts", ["Valid", "Invalid", "N/A", "All"], horizontal=True, key=f"lj_show_{name}")
    date_choice = _range_label(date_range)

    if show == "All":
        fr = rows
    elif show == "N/A":
        fr = [r for r in rows if r.get("validity") in (None, "N/A")]
    else:
        fr = [r for r in rows if r.get("validity") == show]
    fr = [r for r in fr if _in_range(r["date"], date_range)]

    v15_vals = [r["v_15_20"] for r in fr if r.get("v_15_20")]
    lengths = [r for r in fr if r.get("jump_length") is not None]
    times = [r["total_time"] for r in fr if r.get("total_time")]

    own_report = shared_report is None
    date_suffix = f" - {date_choice}" if date_choice != "All dates" else ""
    report = shared_report if shared_report is not None else ReportBuilder(f"Long Jump - {name} ({show} Attempts{date_suffix})", get_brand_color("Long Jump"))
    if shared_report is not None:
        report.heading(f"{name} ({show} Attempts{date_suffix})")

    with st.container(border=True):
        render_metric_row([
            {"label": "Best 15-20m Velocity", "value": f"{max(v15_vals):.2f} m/s" if v15_vals else "-"},
            {"label": "Best Jump Length", "value": f"{max(r['jump_length'] for r in lengths):.2f} m" if lengths else "-"},
            {"label": "Valid Attempt Rate", "value": f"{len(all_valid_rows)}/{len(rows)} ({len(all_valid_rows)/len(rows)*100:.0f}%)" if rows else "-"},
            {"label": "Best 20m Time", "value": f"{min(times):.3f}s" if times else "-"},
        ], COLORS)
        st.caption(f"Showing {show} attempts{date_suffix} ({len(fr)} of {len(rows)} total). Best 20m time is a secondary reference - 15-20m velocity is the stronger predictor of jump distance per research.")
        report.metrics([
            ("Best 15-20m Velocity", f"{max(v15_vals):.2f} m/s" if v15_vals else "-"),
            ("Best Jump Length", f"{max(r['jump_length'] for r in lengths):.2f} m" if lengths else "-"),
            ("Valid Attempt Rate", f"{len(all_valid_rows)}/{len(rows)} ({len(all_valid_rows)/len(rows)*100:.0f}%)" if rows else "-"),
            ("Best 20m Time", f"{min(times):.3f}s" if times else "-"),
        ])
        report.insight(f"Showing {show} attempts ({len(fr)} of {len(rows)} total).")

    if not fr:
        st.info(f"No {show.lower()} attempts to show for this athlete.")
        return

    x_fr = [[r["date"] for r in fr], [r["jump_label"] for r in fr]]

    with st.container(border=True):
        st.markdown("**Split Time by Jump**")
        segments = [
            ("first_10m", "v_0_10", "0-10m", PLOT_COLORS["win"]),
            ("split_10_15", "v_10_15", "10-15m", PLOT_COLORS["sky"]),
            ("split_15_20", "v_15_20", "15-20m", PLOT_COLORS["amber"]),
        ]
        fig = go.Figure()
        # One shared scale for every segment, so the same % change moves each
        # line by the same distance; the biggest change uses ~30% of the
        # thinnest segment, so a line never leaves its own colour band.
        change_by_seg = {field: _time_change_pct(fr, field) for field, _, _, _ in segments}
        biggest = max([abs(p) for ch in change_by_seg.values() for p, _ in ch if p is not None] + [1])
        thinnest = min((r[field] for field, _, _, _ in segments for r in fr if r[field]), default=0)
        room = 0.3 * thinnest
        base = [0.0] * len(fr)
        for field, vfield, label, color in segments:
            heights = [r[field] or 0 for r in fr]
            fig.add_bar(x=x_fr, y=heights, name=label, marker_color=color,
                        hovertemplate=f"{label}: %{{y:.2f}}s<extra></extra>")
            change = change_by_seg[field]
            pct = [p for p, _ in change]
            mids = [b0 + h / 2 for b0, h in zip(base, heights)]
            ys = [m if p is None else m + p / biggest * room for p, m in zip(pct, mids)]
            # One trace per session so a line never runs across into the next session.
            for d in dict.fromkeys(r["date"] for r in fr):
                idx = [i for i, r in enumerate(fr) if r["date"] == d]
                sx = [[x_fr[0][i] for i in idx], [x_fr[1][i] for i in idx]]
                # Dotted "no change" mark through the middle of the segment.
                fig.add_scatter(x=sx, y=[mids[i] for i in idx], mode="lines", showlegend=False, hoverinfo="skip",
                                line=dict(color="rgba(255,255,255,0.5)", width=1, dash="dot"))
                fig.add_scatter(
                    x=sx, y=[ys[i] for i in idx], mode="lines+markers", showlegend=False,
                    line=dict(color="white", width=2),
                    marker=dict(size=8, color=["rgba(0,0,0,0)" if pct[i] is None else "white" for i in idx],
                                line=dict(color="white", width=1.5)),
                    customdata=["first jump of session" if pct[i] is None else
                                f"{pct[i]:+.1f}% vs. {change[i][1]} ("
                                + ("better" if pct[i] < 0 else "worse" if pct[i] > 0 else "no change") + ")" for i in idx],
                    hovertemplate=f"{label} time: %{{customdata}}<extra></extra>",
                )
            base = [b0 + h for b0, h in zip(base, heights)]
        # Legend-only keys for the white lines. Drawn in a mid grey so they
        # read on both the light and dark card (white would vanish in light).
        key_grey = "#8A94A6"
        fig.add_scatter(x=[None], y=[None], mode="lines+markers", name="Time vs. prev jump (lower = faster)",
                        line=dict(color=key_grey, width=2), marker=dict(size=8, color=key_grey))
        fig.add_scatter(x=[None], y=[None], mode="lines", name="No change",
                        line=dict(color=key_grey, width=1, dash="dot"))
        fig.update_layout(
            barmode="stack",
            height=360,
            margin=dict(l=0, r=0, t=10, b=60),
            xaxis_title="Jump number",
            yaxis=dict(title="Time (s)", automargin=True),
            legend=dict(orientation="h", y=1.08, traceorder="normal"),
            **CHART_LAYOUT,
        )
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
        st.plotly_chart(fig, use_container_width=True)
        report.chart("Split Time by Jump", fig)

    with st.container(border=True):
        st.markdown("**Segment Velocity** - how speed builds through the approach")
        fig = go.Figure()
        for seg, label, color in [("v_0_10", "0-10m", PLOT_COLORS["win"]), ("v_10_15", "10-15m", PLOT_COLORS["sky"]), ("v_15_20", "15-20m", PLOT_COLORS["amber"])]:
            fig.add_scatter(x=x_fr, y=[r[seg] for r in fr], name=label, line=dict(color=color, width=1.5), marker=dict(size=8, color=color))
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=20, b=60), yaxis_title="m/s", **CHART_LAYOUT)
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
        st.plotly_chart(fig, use_container_width=True)
        report.chart("Segment Velocity", fig)

    with st.container(border=True):
        st.markdown("**Velocity by Attempt, per Segment**")
        for seg, label, color in [("v_0_10", "0-10m", PLOT_COLORS["win"]), ("v_10_15", "10-15m", PLOT_COLORS["sky"]), ("v_15_20", "15-20m", PLOT_COLORS["amber"])]:
            vals = [r[seg] for r in fr]
            fig = go.Figure(go.Bar(x=x_fr, y=vals, marker_color=color, text=[f"{v:.2f}" if v else "" for v in vals], textposition="outside"))
            fig.update_layout(height=240, margin=dict(l=0, r=0, t=25, b=60), yaxis_title="m/s", title=dict(text=f"{label} Velocity", font=dict(size=13)), **CHART_LAYOUT)
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart(f"{label} Velocity by Attempt", fig)

    dates = sorted({r["date"] for r in fr})
    if len(dates) > 1:
        with st.container(border=True):
            col1, col2 = st.columns(2, gap="large")
            with col1:
                st.markdown("**Consistency** - min/max range of 15-20m velocity per session")
                los, his, means = [], [], []
                for d in dates:
                    vals = [r["v_15_20"] for r in fr if r["date"] == d and r["v_15_20"]]
                    if vals:
                        los.append(min(vals)); his.append(max(vals)); means.append(sum(vals) / len(vals))
                    else:
                        los.append(None); his.append(None); means.append(None)
                fig = go.Figure()
                for d, lo, hi, m in zip(dates, los, his, means):
                    if lo is None:
                        continue
                    fig.add_trace(go.Scatter(x=[d, d], y=[lo, hi], mode="lines", line=dict(color=PLOT_COLORS["muted"], width=6), showlegend=False))
                    fig.add_trace(go.Scatter(x=[d], y=[m], mode="markers", marker=dict(color=PLOT_COLORS["sky"], size=9), showlegend=False))
                fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="m/s", **CHART_LAYOUT)
                fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
                st.plotly_chart(fig, use_container_width=True)
                report.chart("Consistency", fig)

            with col2:
                if lengths:
                    st.markdown("**This Athlete's Velocity vs. Distance**")
                    fig = go.Figure(go.Scatter(
                        x=[r["v_15_20"] for r in lengths], y=[r["jump_length"] for r in lengths],
                        mode="markers", marker=dict(size=10, color=PLOT_COLORS["win"]),
                    ))
                    fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0),
                                       xaxis_title="15-20m velocity (m/s)", yaxis_title="Jump distance (m)", **CHART_LAYOUT)
                    fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
                    st.plotly_chart(fig, use_container_width=True)
                    report.chart("Velocity vs. Distance", fig)
                else:
                    st.info(f"No paired velocity and jump length among the currently shown ({show}) attempts.")

    with st.container(border=True):
        if v15_vals:
            text = f"Current benchmark ({show} attempts): best 15-20m velocity is {max(v15_vals):.2f} m/s."
            st.info(text)
            report.insight(text)
        if lengths:
            best_len = max(r["jump_length"] for r in lengths)
            text = (
                f"Outcome link: the best recorded jump among {show.lower()} attempts is {best_len:.2f} m. Comparing same-day approach velocity "
                f"against distance can suggest a relationship for this athlete, but this should be treated as directional rather than a formula, "
                f"given the limited number of paired data points typically available."
            )
            st.info(text)
            report.insight(text)
        else:
            st.info(f"Outcome link: no jump-length value recorded among {show.lower()} attempts, so approach velocity can't be linked to an outcome here.")
        if show != "N/A" and any(r.get("validity") in (None, "N/A") for r in rows):
            st.warning("Data quality: some attempts have no explicit validity label. Confirm these in Admin before using them for formal benchmarking.")

    with st.container(border=True):
        with st.expander("All Attempts (Including Invalid)"):
            table = [{
                "Date": r["date"], "Jump": r["jump_label"], "First 10m": r["first_10m"],
                "10-15m": r["split_10_15"], "15-20m": r["split_15_20"], "Total": r["total_time"],
                "Validity": r.get("validity") or "N/A", "Length (m)": r.get("jump_length"),
            } for r in rows]
            st.table(table)
        report.table("All Attempts (Including Invalid)", table)

        if own_report:
            report.render_export_controls(f"longjump_{name.replace(' ', '_')}_{show.lower()}", key="report_lj_athlete")
