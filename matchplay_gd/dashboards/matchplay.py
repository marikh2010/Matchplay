import math
from datetime import date
from statistics import median

import streamlit as st
import plotly.graph_objects as go
import db
from match_logic import compute_set_result, compute_match_result
from style import COLORS, PLOT_COLORS, get_brand_ink, CHART_LAYOUT, render_metric_row
from report_export import ReportBuilder



def result_color(result):
    return COLORS["win"] if result == "Win" else (COLORS["lose"] if result == "Lose" else COLORS["muted"])


def render(sport, entry_type):
    athletes = db.list_athletes(sport_id=sport["id"])
    athlete_lookup = {a["name"]: a["id"] for a in athletes}
    athlete_col, view_col, filter_col = st.columns([1.5, 1, 0.8], gap="small")
    with athlete_col:
        selection = st.selectbox("Athlete", ["All players"] + list(athlete_lookup.keys()))
    with view_col:
        category = st.radio("View", ["Tournament", "Training", "Match Breakdown"], horizontal=True)

    if category == "Match Breakdown":
        _render_breakdown_view(selection, athlete_lookup.get(selection))
    elif selection == "All players":
        _render_overview(category)
    else:
        athlete_id = athlete_lookup[selection]
        all_matches = sorted(
            db.get_matches_with_sets(athlete_id=athlete_id, category=category),
            key=lambda match: match["match_date"],
        )
        with filter_col:
            filtered_matches = _render_match_filter(all_matches, athlete_id, category)
        if filtered_matches is not None:
            _render_athlete(selection, athlete_id, category, filtered_matches=filtered_matches)


def _render_overview(category):
    matches = db.get_matches_with_sets(category=category)
    if not matches:
        st.info(f"No {category.lower()} matches logged yet.")
        return
    for m in matches:
        set_results = [compute_set_result(s["player_score"], s["opponent_score"]) for s in m["sets"]]
        m["match_result"], m["score_summary"] = compute_match_result(set_results, m["max_sets"])

    by_athlete = {}
    for m in matches:
        by_athlete.setdefault(m["athletes"]["name"], []).append(m)

    all_names = sorted(by_athlete.keys())
    athlete_lookup_by_name = {p: by_athlete[p][0]["athletes"]["id"] for p in all_names}
    names = all_names

    wins = {p: sum(1 for m in by_athlete[p] if m["match_result"] == "Win") for p in names}
    losses = {p: sum(1 for m in by_athlete[p] if m["match_result"] == "Lose") for p in names}
    avg_load = {p: (sum(m["sets"][0].get("cardio_load") or 0 for m in by_athlete[p] if m["sets"]) / len(by_athlete[p])) if by_athlete[p] else 0 for p in names}
    included_matches = [m for p in names for m in by_athlete[p]]

    report = ReportBuilder(f"Squash - Match Play Overview ({category})", COLORS["win"])

    with st.container(border=True):
        render_metric_row([
            {"label": "Players tracked", "value": len(names)},
            {"label": "Matches recorded", "value": len(included_matches)},
            {"label": "Sets played", "value": sum(len(m["sets"]) for m in included_matches)},
            {"label": "Total match wins", "value": sum(wins.values())},
        ], COLORS)
        report.metrics([("Players tracked", len(names)), ("Matches recorded", len(included_matches)),
                         ("Sets played", sum(len(m["sets"]) for m in included_matches)), ("Total match wins", sum(wins.values()))])

    with st.container(border=True):
        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.subheader("Match Record by Player")
            fig = go.Figure()
            fig.add_bar(name="Wins", y=names, x=[wins[p] for p in names], orientation="h", marker_color=PLOT_COLORS["win"])
            fig.add_bar(name="Losses", y=names, x=[losses[p] for p in names], orientation="h", marker_color=PLOT_COLORS["lose"])
            fig.update_layout(barmode="stack", height=max(260, 40 * len(names)), margin=dict(l=0, r=0, t=10, b=0), **CHART_LAYOUT)
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart("Match Record by Player", fig)
        with col2:
            st.subheader("Average Cardio Load")
            fig = go.Figure(go.Bar(x=names, y=[avg_load[p] for p in names], marker_color=PLOT_COLORS["amber"]))
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), **CHART_LAYOUT)
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart("Average Cardio Load", fig)

    with st.container(border=True):
        report.render_export_controls(f"squash_matchplay_overview_{category.lower()}", key="report_mp_overview")

    with st.container(border=True):
        st.markdown("**Export Individual Athlete Reports**")
        st.caption("Pick one or more athletes to combine their full individual reports into a single export.")
        batch_names = st.multiselect("Select athletes", names, key="mp_batch_export_athletes")
        if batch_names:
            combined = ReportBuilder(f"Squash - Match Play Individual Reports ({category})", COLORS["win"])
            for n in batch_names:
                with st.expander(n, expanded=False):
                    _render_athlete(n, athlete_lookup_by_name[n], category, shared_report=combined)
            with st.container(border=True):
                combined.render_export_controls(f"squash_matchplay_individuals_{category.lower()}", key="report_mp_batch")


def _render_match_breakdown(match, player_name, key=None, points_range=None, hr_range=None):
    """Result badge + score-per-set vs. Avg HR chart for one match. Returns the figure.
    Pass shared ranges so charts shown side by side use the same scales."""
    mr_color = result_color(match["match_result"])
    mr_ink = get_brand_ink(mr_color)
    st.markdown(
        f"<span style='background:{mr_color};color:{mr_ink};padding:3px 10px;border-radius:12px;font-weight:600;'>{match['match_result']} Match</span>"
        f"&nbsp;&nbsp;Score: **{match['score_summary']}**&nbsp;&nbsp;{len(match['sets'])} sets", unsafe_allow_html=True,
    )
    fig = go.Figure()
    fig.add_bar(name=player_name, x=[f"Set {s['set_no']}" for s in match["sets"]], y=[s["player_score"] for s in match["sets"]], marker_color=PLOT_COLORS["blue"])
    fig.add_bar(name=match["opponent_name"], x=[f"Set {s['set_no']}" for s in match["sets"]], y=[s["opponent_score"] for s in match["sets"]], marker_color=PLOT_COLORS["blue_light"])
    fig.add_scatter(
        name="Avg HR",
        x=[f"Set {s['set_no']}" for s in match["sets"]],
        y=[s.get("avg_hr") for s in match["sets"]],
        yaxis="y2",
        line=dict(color=PLOT_COLORS["amber"], shape="spline", smoothing=1.1),
    )
    fig.update_layout(
        height=340,
        margin=dict(l=0, r=10, t=10, b=10),
        xaxis=dict(showgrid=False),
        yaxis=dict(title="Points", showgrid=True, range=points_range, automargin=True),
        yaxis2=dict(title="Avg HR (bpm)", overlaying="y", side="right", showgrid=False, range=hr_range, automargin=True,
                    **(dict(tickmode="linear", dtick=10) if hr_range else {})),
        # Legend in one row under the chart, so it doesn't sit on top of the right-hand HR axis.
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
        **CHART_LAYOUT,
    )
    fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
    st.plotly_chart(fig, use_container_width=True, key=key)
    return fig


def _match_summary(match):
    """Headline numbers for the side-by-side comparison table."""
    sets = match["sets"]
    vals = lambda field: [s[field] for s in sets if s.get(field) is not None]
    avg_hr, peak_hr = vals("avg_hr"), vals("peak_hr")
    rpe = [r for r in vals("rpe") if r]  # 0 = left blank on the original sheet
    duration = int(sum(float(d) for d in vals("duration_seconds")))
    return {
        "Result": f"{match['match_result']} ({match['score_summary']})",
        "Sets played": len(sets),
        "Points won - lost": f"{sum(vals('player_score'))} - {sum(vals('opponent_score'))}",
        "Avg HR (bpm)": f"{sum(avg_hr) / len(avg_hr):.0f}" if avg_hr else "-",
        "Peak HR (bpm)": f"{max(peak_hr)}" if peak_hr else "-",
        "Avg RPE": f"{sum(rpe) / len(rpe):.1f}" if rpe else "-",
        "Total duration": f"{duration // 60}:{duration % 60:02d}" if duration else "-",
    }


def _match_label(match):
    """e.g. 'Tournament - Round 2 - 27/08/2026 - Match 2'."""
    match_date = date.fromisoformat(str(match["match_date"])[:10]).strftime("%d/%m/%Y")
    parts = [match["category"]]
    if match.get("stage") and match["stage"] != match["category"]:
        parts.append(match["stage"])
    parts += [match_date, f"Match {match['match_no']}" if match.get("match_no") else None]
    return " - ".join(p for p in parts if p)


def _render_breakdown_view(selection, athlete_id):
    """Every match against one opponent, Tournament and Training together."""
    matches = sorted(db.get_matches_with_sets(athlete_id=athlete_id), key=lambda m: m["match_date"])
    matches = [m for m in matches if m.get("opponent_name") and m["sets"]]
    if not matches:
        st.info("No matches logged yet." if athlete_id is None else f"No matches logged yet for {selection}.")
        return
    opponents = sorted({m["opponent_name"] for m in matches})
    opponent = st.selectbox("Opponent", opponents, key=f"mp_breakdown_opponent_{athlete_id}")
    vs_matches = [m for m in matches if m["opponent_name"] == opponent]
    for m in vs_matches:
        set_results = [compute_set_result(s["player_score"], s["opponent_score"]) for s in m["sets"]]
        m["match_result"], m["score_summary"] = compute_match_result(set_results, m["max_sets"])

    title = f"{selection} vs {opponent}" if athlete_id is not None else f"Matches vs {opponent}"
    report = ReportBuilder(f"Squash - Match Breakdown - {title}", COLORS["win"])
    st.subheader(title)
    st.caption(f"{len(vs_matches)} match{'es' if len(vs_matches) != 1 else ''} - Tournament and Training combined")
    labels = [_match_label(m) if athlete_id is not None else f"{m['athletes']['name']} - {_match_label(m)}" for m in vs_matches]

    with st.container(border=True):
        st.markdown("**Overall Trend** - every match vs this opponent, oldest to newest")
        fig = _render_opponent_trend(vs_matches, labels)
        report.chart(f"Overall Trend vs {opponent}", fig)

    if len(vs_matches) == 1:
        compare = [0]
    else:
        st.markdown("**Compare two matches**")
        col_a, col_b = st.columns(2, gap="large")
        idx = list(range(len(vs_matches)))
        with col_a:
            a = st.selectbox("Match A", idx, index=len(idx) - 2, format_func=lambda i: labels[i], key=f"mp_cmp_a_{athlete_id}_{opponent}")
        with col_b:
            b = st.selectbox("Match B", idx, index=len(idx) - 1, format_func=lambda i: labels[i], key=f"mp_cmp_b_{athlete_id}_{opponent}")
        if a == b:
            st.warning("Pick two different matches to compare.")
            compare = [a]
        else:
            compare = [a, b]
    chosen_matches = [vs_matches[i] for i in compare]
    chosen_labels = [labels[i] for i in compare]

    with st.container(border=True):
        st.markdown("**Comparison**")
        summaries = [_match_summary(m) for m in chosen_matches]
        table = {"": list(summaries[0].keys())} | {label: [str(v) for v in s.values()] for label, s in zip(chosen_labels, summaries)}
        st.dataframe(table, hide_index=True, use_container_width=True)
        report.metrics([(f"{label} - {k}", v) for label, s in zip(chosen_labels, summaries) for k, v in s.items()])

    # Shared scales so the side-by-side charts compare like for like.
    all_sets = [s for m in chosen_matches for s in m["sets"]]
    max_points = max([s[f] or 0 for s in all_sets for f in ("player_score", "opponent_score")] + [11])
    hrs = [s["avg_hr"] for s in all_sets if s.get("avg_hr") is not None]
    # Round to whole tens so the HR axis reads 160 / 170 / 180..., not 170.3.
    hr_range = [math.floor((min(hrs) - 5) / 10) * 10, math.ceil((max(hrs) + 5) / 10) * 10] if hrs else None

    cols = st.columns(2, gap="large")
    for col, m, label in zip(cols, chosen_matches, chosen_labels):
        with col, st.container(border=True):
            st.markdown(f"**{label}**")
            fig = _render_match_breakdown(m, m["athletes"]["name"], key=f"mp_breakdown_{m['id']}",
                                          points_range=[0, max_points + 1], hr_range=hr_range)
        report.chart(f"{label} ({m['match_result']}, {m['score_summary']})", fig)

    with st.container(border=True):
        report.render_export_controls(f"squash_match_breakdown_{opponent.replace(' ', '_')}", key="report_mp_breakdown")


def _render_opponent_trend(matches, labels):
    """% of points won (marker colour = result, shape = Tournament/Training) and Avg HR, match by match."""
    x = [f"{date.fromisoformat(str(m['match_date'])[:10]).strftime('%d/%m/%y')}<br>{m['category']} M{m.get('match_no') or ''}" for m in matches]
    points_won_pct, avg_hrs, durations = [], [], []
    for m in matches:
        summary = _match_summary(m)
        won = sum(s["player_score"] or 0 for s in m["sets"])
        lost = sum(s["opponent_score"] or 0 for s in m["sets"])
        points_won_pct.append(round(won / (won + lost) * 100, 1) if won + lost else None)
        avg_hrs.append(None if summary["Avg HR (bpm)"] == "-" else int(summary["Avg HR (bpm)"]))
        durations.append(summary["Total duration"])

    fig = go.Figure()
    fig.add_scatter(
        x=x, y=points_won_pct, name="Points won %", mode="lines+markers",
        line=dict(color=PLOT_COLORS["blue"]),
        marker=dict(
            size=13, line=dict(width=1, color="white"),
            color=[PLOT_COLORS["win"] if m["match_result"] == "Win" else PLOT_COLORS["lose"] if m["match_result"] == "Lose" else COLORS["muted"] for m in matches],
            symbol=["diamond" if m["category"] == "Tournament" else "circle" for m in matches],
        ),
        customdata=[[label, m["match_result"], m["score_summary"], d] for m, label, d in zip(matches, labels, durations)],
        hovertemplate="%{customdata[0]}<br>%{customdata[1]} (%{customdata[2]})<br>Points won: %{y:.1f}%<br>Duration: %{customdata[3]}<extra></extra>",
    )
    fig.add_scatter(
        x=x, y=avg_hrs, name="Avg HR", yaxis="y2", mode="lines+markers",
        line=dict(color=PLOT_COLORS["amber"], dash="dot"),
        hovertemplate="Avg HR: %{y} bpm<extra></extra>",
    )
    fig.add_hline(y=50, line=dict(color=COLORS["muted"], width=1, dash="dash"))
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(title="Points won (%)", ticksuffix="%", showgrid=True),
        yaxis2=dict(title="Avg HR (bpm)", overlaying="y", side="right", showgrid=False),
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig, use_container_width=True, key="mp_opponent_trend")
    st.caption("Marker colour = result (Win / Lose). Diamond = Tournament, circle = Training. Dashed line = 50% of points won.")
    return fig


def _as_percent(value):
    """Avg HR % from the Sheet: 95, "95", "95%", or 0.95 (a %-formatted cell) -> 95.0."""
    if value is None or value == "":
        return None
    try:
        value = float(str(value).strip().rstrip("%"))
    except ValueError:
        return None
    return value * 100 if value <= 1.5 else value


def _implied_hr_max(sets):
    """HR max implied by the entered Avg HR bpm / %HRmax pairs. Median, so a
    single mistyped percentage doesn't skew it."""
    implied = sorted(s["avg_hr"] / s["avg_hr_pct"] * 100 for s in sets if s.get("avg_hr") and s.get("avg_hr_pct"))
    return round(median(implied)) if implied else None


def _render_match_filter(all_matches, athlete_id, category):
    if not all_matches:
        st.info(f"No {category.lower()} matches logged yet for this athlete.")
        return None

    available_dates = sorted({date.fromisoformat(str(match["match_date"])[:10]) for match in all_matches})
    opponents = sorted({match["opponent_name"] for match in all_matches if match.get("opponent_name")})
    with st.popover("Filter", use_container_width=True):
        filter_by = st.radio(
            "Filter by",
            ["Date", "Opponent"],
            horizontal=True,
            key=f"mp_filter_by_{athlete_id}_{category.lower()}",
        )
        if filter_by == "Date":
            available_date_options = [None, *available_dates]
            start_date = st.selectbox(
                "From (recorded dates)",
                available_date_options,
                format_func=lambda value: "Choose a date" if value is None else value.strftime("%d/%m/%Y"),
                key=f"mp_timeline_from_{athlete_id}_{category.lower()}",
            )
            if start_date is None:
                st.caption("Choose one date or add an end date for a range.")
                return None
            end_date = st.selectbox(
                "To (optional)",
                [None, *[available_date for available_date in available_dates if available_date >= start_date]],
                format_func=lambda value: "Same day" if value is None else value.strftime("%d/%m/%Y"),
                key=f"mp_timeline_to_{athlete_id}_{category.lower()}",
            ) or start_date
            return [
                match for match in all_matches
                if start_date <= date.fromisoformat(str(match["match_date"])[:10]) <= end_date
            ]

        if not opponents:
            st.caption("No opponent names have been recorded.")
            return None
        opponent = st.selectbox(
            "Opponent",
            [None, *opponents],
            format_func=lambda value: "Choose an opponent" if value is None else value,
            key=f"mp_opponent_{athlete_id}_{category.lower()}",
        )
        if opponent is None:
            return None
        return [match for match in all_matches if match.get("opponent_name") == opponent]


def _render_athlete(selection, athlete_id, category, shared_report=None, all_matches=None, filtered_matches=None):
    if all_matches is None:
        all_matches = sorted(db.get_matches_with_sets(athlete_id=athlete_id, category=category), key=lambda m: m["match_date"])
    if not all_matches:
        st.info(f"No {category.lower()} matches logged yet for {selection}.")
        return

    if filtered_matches is None:
        filtered_matches = _render_match_filter(all_matches, athlete_id, category)
        if filtered_matches is None:
            return
    matches = filtered_matches
    if not matches:
        st.info("No matches match the selected filter.")
        return

    for m in matches:
        set_results = [compute_set_result(s["player_score"], s["opponent_score"]) for s in m["sets"]]
        m["match_result"], m["score_summary"] = compute_match_result(set_results, m["max_sets"])

    match_wins = sum(1 for m in matches if m["match_result"] == "Win")
    match_losses = sum(1 for m in matches if m["match_result"] == "Lose")

    all_sets = []
    for m in matches:
        for s in m["sets"]:
            all_sets.append({"label": f"{m['opponent_name'][:10]} S{s['set_no']}", **s, "avg_hr_pct": _as_percent(s.get("avg_hr_pct"))})

    sets_won = sum(1 for s in all_sets if compute_set_result(s["player_score"], s["opponent_score"]) == "Win")
    sets_lost = sum(1 for s in all_sets if compute_set_result(s["player_score"], s["opponent_score"]) == "Lose")
    avg_hrs = [s["avg_hr"] for s in all_sets if s.get("avg_hr") is not None]
    peak_hrs = [s["peak_hr"] for s in all_sets if s.get("peak_hr") is not None]

    st.subheader(selection)
    own_report = shared_report is None
    report = shared_report if shared_report is not None else ReportBuilder(f"Squash - Match Play - {selection} ({category})", COLORS["win"])
    if shared_report is not None:
        report.heading(f"{selection} ({category})")

    with st.container(border=True):
        render_metric_row([
            {"label": "Matches Won", "value": f"{match_wins} / {match_wins + match_losses}"},
            {"label": "Sets Won - Lost", "value": f"{sets_won} - {sets_lost}"},
            {"label": "Avg Heart Rate", "value": f"{sum(avg_hrs)/len(avg_hrs):.0f} bpm" if avg_hrs else "-"},
            {"label": "Peak Heart Rate", "value": f"{max(peak_hrs):.0f} bpm" if peak_hrs else "-"},
        ], COLORS)
        report.metrics([
            ("Matches Won", f"{match_wins} / {match_wins + match_losses}"), ("Sets Won - Lost", f"{sets_won} - {sets_lost}"),
            ("Avg Heart Rate", f"{sum(avg_hrs)/len(avg_hrs):.0f} bpm" if avg_hrs else "-"),
            ("Peak Heart Rate", f"{max(peak_hrs):.0f} bpm" if peak_hrs else "-"),
        ])

    with st.container(border=True):
        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.markdown("**Heart Rate Trend** - Avg / Peak HR, set by set")
            fig = go.Figure()
            fig.add_scatter(
                x=[s["label"] for s in all_sets],
                y=[s.get("avg_hr") for s in all_sets],
                name="Avg HR",
                line=dict(color=PLOT_COLORS["sky"], shape="spline", smoothing=1.1),
            )
            fig.add_scatter(
                x=[s["label"] for s in all_sets],
                y=[s.get("peak_hr") for s in all_sets],
                name="Peak HR",
                line=dict(color=PLOT_COLORS["lose"], shape="spline", smoothing=1.1),
            )
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="bpm", **CHART_LAYOUT)
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart("Heart Rate Trend", fig)
        with col2:
            st.markdown("**Recovery** - Recovery drop (bar) vs. End / 1-min Recovery HR (lines)")
            fig = go.Figure()
            fig.add_bar(x=[s["label"] for s in all_sets], y=[(s.get("end_hr") or 0) - (s.get("hr_recovery") or 0) for s in all_sets],
                        name="Recovery Drop (bpm)", marker_color=PLOT_COLORS["amber"] + "55")
            fig.add_scatter(x=[s["label"] for s in all_sets], y=[s.get("end_hr") for s in all_sets], name="End HR", line=dict(color=PLOT_COLORS["win"]), yaxis="y2")
            fig.add_scatter(x=[s["label"] for s in all_sets], y=[s.get("hr_recovery") for s in all_sets], name="1-min Recovery HR", line=dict(color=PLOT_COLORS["sky"], dash="dot"), yaxis="y2")
            fig.update_layout(
                height=340, margin=dict(l=0, r=10, t=10, b=70),
                xaxis=dict(showgrid=False),
                yaxis=dict(title="Recovery drop (bpm)", showgrid=True),
                yaxis2=dict(title="Heart rate (bpm)", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5),
                **CHART_LAYOUT,
            )
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart("Recovery", fig)

    hr_max = _implied_hr_max(all_sets)
    if hr_max:
        with st.container(border=True):
            st.markdown("**Heart Rate Trend (% HR max)** - Avg / Peak HR, set by set")
            st.caption(f"Avg HR % as entered. Peak HR % uses HR max ≈ {hr_max} bpm, implied by the Avg HR bpm / % values.")
            pct = lambda hr: round(hr / hr_max * 100, 1) if hr is not None else None
            fig = go.Figure()
            fig.add_scatter(
                x=[s["label"] for s in all_sets],
                y=[s.get("avg_hr_pct") for s in all_sets],
                name="Avg HR %",
                line=dict(color=PLOT_COLORS["sky"], shape="spline", smoothing=1.1),
            )
            fig.add_scatter(
                x=[s["label"] for s in all_sets],
                y=[pct(s.get("peak_hr")) for s in all_sets],
                name="Peak HR %",
                line=dict(color=PLOT_COLORS["lose"], shape="spline", smoothing=1.1),
            )
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(title="% HR max", ticksuffix="%"), **CHART_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)
            report.chart(f"Heart Rate Trend (% HR max, HR max ≈ {hr_max} bpm)", fig)

    with st.container(border=True):
        col3, col4 = st.columns(2, gap="large")
        with col3:
            st.markdown("**Cardio Load** - per match")
            loads = [m["sets"][0].get("cardio_load") if m["sets"] else None for m in matches]
            fig = go.Figure(go.Bar(x=[m["opponent_name"] for m in matches], y=loads, marker_color=PLOT_COLORS["blue"]))
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), **CHART_LAYOUT)
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart("Cardio Load per Match", fig)
        with col4:
            st.markdown("**Set Margin** - point difference, set by set")
            margins = [(s["player_score"] - s["opponent_score"]) if s["player_score"] is not None and s["opponent_score"] is not None else None for s in all_sets]
            margin_colors = [PLOT_COLORS["blue_light"] if margin is not None and margin > 0 else PLOT_COLORS["sky"] for margin in margins]
            fig = go.Figure(go.Bar(x=[s["label"] for s in all_sets], y=margins, marker_color=margin_colors))
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="Point margin", **CHART_LAYOUT)
            fig.update_traces(selector=dict(type="bar"), marker_cornerradius=8)
            st.plotly_chart(fig, use_container_width=True)
            report.chart("Set Margin", fig)

    with st.container(border=True):
        st.markdown("**Match Breakdown** - score per set vs. average heart rate")
        options = {f"{m['stage']} - vs {m['opponent_name']} ({m['match_date']})": m for m in matches}
        chosen = options[st.selectbox("Match", list(options.keys()), index=len(options) - 1)]
        fig = _render_match_breakdown(chosen, selection)
        report.insight(f"Match breakdown shown: {chosen['match_result']} against {chosen['opponent_name']}, final score {chosen['score_summary']}.")
        report.chart(f"Match Breakdown - vs {chosen['opponent_name']}", fig)

    with st.container(border=True):
        if own_report:
            report.render_export_controls(f"squash_matchplay_{selection.replace(' ', '_')}_{category.lower()}", key="report_mp_athlete")
