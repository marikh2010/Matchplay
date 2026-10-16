import streamlit as st
import plotly.graph_objects as go
import db
from rsa_logic import compute_peak_time, compute_duration, compute_fatigue_index, rate_peak_time, rate_fatigue_index
from style import COLORS, PLOT_COLORS, CHART_LAYOUT, render_metric_row
from report_export import ReportBuilder

RATING_COLOR = {"Good": PLOT_COLORS["win"], "Average": PLOT_COLORS["amber"], "Bad": PLOT_COLORS["lose"], None: PLOT_COLORS["muted"]}
_NORMATIVE_TABLE = [
    {"Metric": "Peak time (Male)", "Good": "< 21.0s", "Average": "21.0-24.0s", "Bad": ">= 24.0s"},
    {"Metric": "Peak time (Female)", "Good": "< 23.5s", "Average": "23.5-26.5s", "Bad": ">= 26.5s"},
    {"Metric": "Fatigue index", "Good": "< 4.5%", "Average": "4.5-8.0%", "Bad": ">= 8.0%"},
]


def _set_colors(totals):
    n = len(totals)
    order = sorted(range(n), key=lambda i: totals[i])
    colors = [None] * n
    for rank, idx in enumerate(order):
        frac = rank / max(n - 1, 1)
        colors[idx] = PLOT_COLORS["win"] if frac < 1 / 3 else PLOT_COLORS["amber"] if frac < 2 / 3 else PLOT_COLORS["lose"]
    return colors


def _summarize(test):
    totals = [s["lap_1"] + s["lap_2"] for s in test["sets"] if s.get("lap_1") is not None and s.get("lap_2") is not None]
    if not totals:
        return None
    return {"test": test, "sets": test["sets"], "totals": totals,
            "duration": compute_duration(totals), "peak": compute_peak_time(totals), "fatigue": compute_fatigue_index(totals)}


def render(sport, entry_type):
    athletes = db.list_athletes(sport_id=sport["id"])
    athlete_lookup = {a["name"]: a for a in athletes}
    selection = st.selectbox("Athlete", ["All athletes"] + list(athlete_lookup.keys()))

    if selection == "All athletes":
        _render_overview()
    else:
        _render_athlete(selection, athlete_lookup[selection])


def _render_overview():
    tests = db.get_rsa_tests_with_sets()
    if not tests:
        st.info("No RSA tests logged yet.")
        return
    summaries = [s for s in (_summarize(t) for t in tests) if s]
    by_athlete = {}
    for s in summaries:
        by_athlete.setdefault(s["test"]["athletes"]["name"], []).append(s)

    all_names = sorted(by_athlete.keys())
    athlete_lookup_by_name = {n: by_athlete[n][0]["test"]["athletes"] for n in all_names}
    names = all_names

    latest_peak = {n: sorted(by_athlete[n], key=lambda s: s["test"]["test_date"])[-1]["peak"] for n in names}
    included_summaries = [s for n in names for s in by_athlete[n]]

    report = ReportBuilder("Squash - RSA Test Overview", COLORS["win"])

    with st.container(border=True):
        render_metric_row([
            {"label": "Athletes Tested", "value": len(names)},
            {"label": "Tests Recorded", "value": len(included_summaries)},
        ], COLORS)
        report.metrics([("Athletes Tested", len(names)), ("Tests Recorded", len(included_summaries))])

    with st.container(border=True):
        st.markdown("**Most Recent Peak Time by Athlete**")
        fig = go.Figure(go.Bar(x=names, y=[latest_peak[n] for n in names], marker_color=PLOT_COLORS["sky"]))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="seconds", **CHART_LAYOUT)
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
        st.plotly_chart(fig, use_container_width=True)
        report.chart("Most Recent Peak Time by Athlete", fig)

    with st.container(border=True):
        report.render_export_controls("squash_rsa_overview", key="report_rsa_overview")

    with st.container(border=True):
        st.markdown("**Export Individual Athlete Reports**")
        st.caption("Pick one or more athletes to combine their full individual reports into a single export.")
        batch_names = st.multiselect("Select athletes", names, key="rsa_batch_export_athletes")
        if batch_names:
            combined = ReportBuilder("Squash - RSA Test Individual Reports", COLORS["win"])
            for n in batch_names:
                with st.expander(n, expanded=False):
                    _render_athlete(n, athlete_lookup_by_name[n], shared_report=combined)
            with st.container(border=True):
                combined.render_export_controls("squash_rsa_individuals", key="report_rsa_batch")


def _render_athlete(athlete_name, athlete, shared_report=None):
    gender = athlete.get("gender")
    if not gender:
        st.warning(f"{athlete_name} doesn't have a gender set yet, so results can't be rated. Fix this in Admin.")

    tests = db.get_rsa_tests_with_sets(athlete_id=athlete["id"])
    summaries = [s for s in (_summarize(t) for t in tests) if s]
    if not summaries:
        st.info(f"No complete RSA tests logged yet for {athlete_name}.")
        return
    summaries.sort(key=lambda s: s["test"]["test_date"])

    def label_for(s):
        stage = s["test"]["stage"] or "Test"
        return f"{s['test']['test_date']} - {stage}"

    st.subheader(f"{athlete_name}" + (f" - {gender}" if gender else ""))

    labels = [label_for(s) for s in summaries]

    own_report = shared_report is None
    report = shared_report if shared_report is not None else ReportBuilder(f"Squash - RSA Test - {athlete_name}", COLORS["win"])
    if shared_report is not None:
        report.heading(athlete_name)

    if len(summaries) == 1:
        st.info("Only one complete test logged - log another test to see a Pre vs. Post comparison.")
        _render_test_detail(athlete_name, gender, summaries[0], labels[0], "Test", report, include_bands=True)
    else:
        col_pre, col_post = st.columns(2, gap="large")
        with col_pre:
            pre_label = st.selectbox("Pre (earlier date)", labels, index=len(labels) - 2, key=f"rsa_pre_{athlete_name}")
        post_options = [l for l in labels if l != pre_label]
        with col_post:
            post_label = st.selectbox("Post (later date)", post_options, index=len(post_options) - 1, key=f"rsa_post_{athlete_name}")
        # Keep Pre as the earlier test even if the dates are picked the other way round.
        if labels.index(pre_label) > labels.index(post_label):
            pre_label, post_label = post_label, pre_label
            st.caption("Dates were swapped so Pre is the earlier test.")
        pre = summaries[labels.index(pre_label)]
        post = summaries[labels.index(post_label)]

        _render_comparison(athlete_name, pre, post, pre_label, post_label, summaries, report)
        _render_test_detail(athlete_name, gender, pre, pre_label, "Pre", report)
        _render_test_detail(athlete_name, gender, post, post_label, "Post", report, include_bands=True)

    with st.container(border=True):
        if own_report:
            report.render_export_controls(f"squash_rsa_{athlete_name.replace(' ', '_')}", key="report_rsa_athlete")


def _render_comparison(athlete_name, pre, post, pre_label, post_label, summaries, report):
    st.markdown("#### Comparison (Overall)")
    report.heading(f"Comparison: {pre_label} vs. {post_label}")

    with st.container(border=True):
        d_dur = post["duration"] - pre["duration"]
        d_peak = post["peak"] - pre["peak"]
        d_fat = post["fatigue"] - pre["fatigue"]
        render_metric_row([
            {"label": "Duration", "value": f"{post['duration']:.1f}s", "delta": f"{'↓' if d_dur < 0 else '↑'} {abs(d_dur):.2f}s", "status": "good" if d_dur < 0 else "bad" if d_dur > 0 else None},
            {"label": "Peak", "value": f"{post['peak']:.2f}s", "delta": f"{'↓' if d_peak < 0 else '↑'} {abs(d_peak):.2f}s", "status": "good" if d_peak < 0 else "bad" if d_peak > 0 else None},
            {"label": "Fatigue Index", "value": f"{post['fatigue']:.1f}%", "delta": f"{'↓' if d_fat < 0 else '↑'} {abs(d_fat):.2f}pp", "status": "good" if d_fat < 0 else "bad" if d_fat > 0 else None},
        ], COLORS)
        st.caption(f"Post values ({post_label}); arrows show the change from Pre ({pre_label}). Lower is better.")
        report.insight(f"Post ({post_label}) vs. Pre ({pre_label}): duration changed {d_dur:+.2f}s, peak changed {d_peak:+.2f}s, and fatigue index changed {d_fat:+.2f} percentage points.")

    with st.container(border=True):
        st.markdown("**Set Totals - Pre vs. Post**")
        n_sets = max(len(pre["totals"]), len(post["totals"]))
        set_labels = [f"S{i+1}" for i in range(n_sets)]
        fig = go.Figure()
        fig.add_bar(x=set_labels[:len(pre["totals"])], y=pre["totals"], name=f"Pre - {pre_label}", marker_color=PLOT_COLORS["muted"])
        fig.add_bar(x=set_labels[:len(post["totals"])], y=post["totals"], name=f"Post - {post_label}", marker_color=PLOT_COLORS["sky"])
        fig.update_layout(barmode="group", height=260, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="seconds",
                          legend=dict(orientation="h", y=1.12), **CHART_LAYOUT)
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
        st.plotly_chart(fig, use_container_width=True, key=f"rsa_cmp_sets_{athlete_name}")
        report.chart("Set Totals - Pre vs. Post", fig)

        cmp_rows = []
        for i in range(n_sets):
            b = pre["totals"][i] if i < len(pre["totals"]) else None
            a = post["totals"][i] if i < len(post["totals"]) else None
            cmp_rows.append({"Set": i + 1, "Pre (s)": b, "Post (s)": a,
                             "Change (s)": round(a - b, 2) if a is not None and b is not None else None})
        with st.expander("Set-by-Set Comparison"):
            st.table(cmp_rows)
        report.table("Set-by-Set Comparison", cmp_rows)

    if len(summaries) > 2:
        with st.container(border=True):
            st.markdown("**Full History** - peak time and fatigue index across all tests")
            fig2 = go.Figure()
            fig2.add_scatter(x=[s["test"]["test_date"] for s in summaries], y=[s["peak"] for s in summaries],
                              name="Peak time (s)", line=dict(color=PLOT_COLORS["win"]))
            fig2.add_scatter(x=[s["test"]["test_date"] for s in summaries], y=[s["fatigue"] for s in summaries],
                              name="Fatigue index (%)", yaxis="y2", line=dict(color=PLOT_COLORS["lose"]))
            fig2.update_layout(
                height=260, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(title="Peak time (s)"), yaxis2=dict(title="Fatigue index (%)", overlaying="y", side="right"),
                **CHART_LAYOUT,
            )
            st.plotly_chart(fig2, use_container_width=True, key=f"rsa_history_{athlete_name}")
            report.chart("Full History", fig2)


def _render_test_detail(athlete_name, gender, chosen, chosen_label, section, report, include_bands=False):
    """One test's full breakdown - the same layout the dashboard used before
    the comparison was added. Rendered once for Pre and once for Post."""
    st.markdown(f"#### {section} - {chosen_label}")
    report.heading(f"{section}: {chosen_label}")

    peak_rating = rate_peak_time(chosen["peak"], gender)
    fatigue_rating = rate_fatigue_index(chosen["fatigue"])
    _rating_status = {"Good": "good", "Average": "warning", "Bad": "bad"}
    key = f"{section.lower()}_{athlete_name}"

    with st.container(border=True):
        render_metric_row([
            {"label": "Duration", "value": f"{chosen['duration']:.1f}s"},
            {"label": "Peak", "value": f"{chosen['peak']:.2f}s", "caption": peak_rating or "No gender set", "status": _rating_status.get(peak_rating)},
            {"label": "Fatigue Index", "value": f"{chosen['fatigue']:.1f}%", "caption": fatigue_rating, "status": _rating_status.get(fatigue_rating)},
        ], COLORS)
        report.metrics([
            ("Duration", f"{chosen['duration']:.1f}s"),
            ("Peak", f"{chosen['peak']:.2f}s ({peak_rating or 'No gender set'})"),
            ("Fatigue Index", f"{chosen['fatigue']:.1f}% ({fatigue_rating})"),
        ])

        colors = _set_colors(chosen["totals"])
        fig = go.Figure(go.Bar(x=[f"S{i+1}" for i in range(len(chosen['totals']))], y=chosen["totals"], marker_color=colors))
        fig.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0), **CHART_LAYOUT)
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
        st.plotly_chart(fig, use_container_width=True, key=f"rsa_sets_{key}")
        report.chart(f"{section} - Set Totals", fig)

        with st.expander("Set-by-Set Splits"):
            rows = [{"Set": i + 1, "Lap 1": s.get("lap_1"), "Lap 2": s.get("lap_2"), "Total": t}
                    for i, (s, t) in enumerate(zip(chosen["sets"], chosen["totals"]))]
            st.table(rows)
            report.table(f"{section} - Set-by-Set Splits", rows)

    with st.container(border=True):
        col_chart, col_table = st.columns([1.3, 1], gap="large")
        with col_chart:
            st.markdown("**This Test's Rating**")
            fig3 = go.Figure()
            fig3.add_bar(x=["Peak Time"], y=[chosen["peak"]], marker_color=RATING_COLOR.get(peak_rating))
            fig3.add_bar(x=["Fatigue Index"], y=[chosen["fatigue"]], marker_color=RATING_COLOR.get(fatigue_rating))
            fig3.update_layout(height=240, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, **CHART_LAYOUT)
            fig3.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig3, use_container_width=True, key=f"rsa_rating_{key}")
        with col_table:
            st.markdown("**Normative Bands Used**")
            st.table(_NORMATIVE_TABLE)
            if include_bands:
                report.table("Normative Bands Used", _NORMATIVE_TABLE)
