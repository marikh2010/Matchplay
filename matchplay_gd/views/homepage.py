import datetime
import time
import streamlit as st
import db
from style import apply_style, COLORS, render_metric_row

# Entry types whose ratings depend on the athlete's sex, so a missing value
# is worth flagging for that sport.
_SEX_RATED = {"RSA Test", "Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test", "Judo Fitness Test"}
ACTIVE_DAYS = 30
REFRESH_SECONDS = 30  # how often the homepage re-checks the Sheet for edits


def _records():
    """Every logged record across all test types, as (entry_type_id, athlete_id, date)."""
    sources = [
        (db.get_matches(), "match_date"),
        (db.get_rsa_tests(), "test_date"),
        (db.get_yoyo_tests(), "test_date"),
        (db.get_longjump_tests(), "test_date"),
        (db.get_judo_tests(), "test_date"),
    ]
    out = []
    for rows, date_key in sources:
        for r in rows:
            d = r.get(date_key)
            try:
                d = datetime.date.fromisoformat(str(d)[:10]) if d else None
            except ValueError:
                d = None
            out.append({"entry_type_id": r.get("entry_type_id"), "athlete_id": r.get("athlete_id"), "date": d})
    return out


def _ago(d, today):
    days = (today - d).days
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"


def _fmt_date(d, today):
    return f"{d.strftime('%d %b %Y')} ({_ago(d, today)})" if d else "-"


def _sex_counts(athletes):
    male = sum(1 for a in athletes if a.get("gender") == "Male")
    female = sum(1 for a in athletes if a.get("gender") == "Female")
    return male, female, len(athletes) - male - female


def _sex_caption(athletes):
    male, female, unset = _sex_counts(athletes)
    return f"{male} male · {female} female" + (f" · {unset} not set" if unset else "")


def _athlete_issues(athletes, entry_types, et_ids, tested, lj_tests, rsa_tests):
    """What's missing for each athlete in this sport: {athlete_id: [reasons]}."""
    sex_rated = any(et["name"] in _SEX_RATED for et in entry_types)
    issues = {a["id"]: [] for a in athletes}
    for a in athletes:
        if not a.get("gender"):
            issues[a["id"]].append("no sex set" + (" (results can't be rated)" if sex_rated else ""))
        if a["id"] not in tested:
            issues[a["id"]].append("no records yet")
    for t in lj_tests:
        if t.get("entry_type_id") in et_ids and t.get("athlete_id") in issues:
            n = sum(1 for att in t["attempts"] if att.get("validity") in (None, "", "N/A"))
            if n:
                issues[t["athlete_id"]].append(n)  # summed below
    for t in rsa_tests:
        if t.get("entry_type_id") in et_ids and t.get("athlete_id") in issues:
            if not t["sets"] or any(st_.get("lap_1") is None or st_.get("lap_2") is None for st_ in t["sets"]):
                issues[t["athlete_id"]].append(f"RSA test on {t['test_date']} has missing lap times")
    out = {}
    for aid, reasons in issues.items():
        unlabelled = sum(r for r in reasons if isinstance(r, int))
        text = [r for r in reasons if not isinstance(r, int)]
        if unlabelled:
            text.append(f"{unlabelled} long jump attempt(s) with no Valid/Invalid label")
        if text:
            out[aid] = text
    return out


def render():
    apply_style()
    st.title("Matchplay Tracker")
    st.caption("Admin summary of every sport: who's set up, what's been logged, and what needs fixing.")
    _summary()


@st.fragment(run_every=REFRESH_SECONDS)
def _summary():
    """Re-runs on its own every REFRESH_SECONDS, picking up Sheet edits."""
    loaded_at = db.refresh_if_older_than(REFRESH_SECONDS)
    st.caption(f"Last updated {time.strftime('%H:%M:%S', time.localtime(loaded_at))} · "
               f"checks for changes every {REFRESH_SECONDS} seconds")

    sports = db.list_sports()
    if not sports:
        st.info("No sports set up yet. Head to Admin to add one.")
        return

    today = datetime.date.today()
    records = _records()
    all_athletes = db.list_athletes()
    last_overall = max((r["date"] for r in records if r["date"]), default=None)
    lj_tests = db.get_longjump_tests_with_attempts()
    rsa_tests = db.get_rsa_tests_with_sets()

    with st.container(border=True):
        render_metric_row([
            {"label": "Sports", "value": len(sports)},
            {"label": "Athletes", "value": len(all_athletes), "caption": _sex_caption(all_athletes)},
            {"label": "Records Logged", "value": len(records)},
            {"label": "Last Entry", "value": last_overall.strftime("%d %b %Y") if last_overall else "-"},
        ], COLORS)

    for sport in sports:
        entry_types = db.list_entry_types(sport["id"])
        athletes = db.list_athletes(sport_id=sport["id"])
        et_ids = {et["id"] for et in entry_types}
        sport_records = [r for r in records if r["entry_type_id"] in et_ids]
        last = max((r["date"] for r in sport_records if r["date"]), default=None)
        recent = {r["athlete_id"] for r in sport_records if r["date"] and (today - r["date"]).days <= ACTIVE_DAYS}
        tested = {r["athlete_id"] for r in sport_records}
        issues = _athlete_issues(athletes, entry_types, et_ids, tested, lj_tests, rsa_tests)

        with st.container(border=True):
            st.subheader(sport["name"])
            render_metric_row([
                {"label": "Athletes", "value": len(athletes), "caption": _sex_caption(athletes)},
                {"label": "Records Logged", "value": len(sport_records)},
                {"label": f"Active (last {ACTIVE_DAYS} days)", "value": f"{len(recent)} of {len(athletes)}"},
                {"label": "Incomplete Data", "value": f"{len(issues)} of {len(athletes)}",
                 "caption": "athletes need fixing" if issues else "all complete",
                 "status": "warning" if issues else "good"},
                {"label": "Last Entry", "value": last.strftime("%d %b %Y") if last else "-",
                 "caption": _ago(last, today) if last else "Nothing logged yet"},
            ], COLORS)

            if entry_types:
                rows = []
                for et in entry_types:
                    et_records = [r for r in sport_records if r["entry_type_id"] == et["id"]]
                    et_last = max((r["date"] for r in et_records if r["date"]), default=None)
                    rows.append({
                        "Test": et["name"],
                        "Records": len(et_records),
                        "Athletes Tested": f"{len({r['athlete_id'] for r in et_records})} of {len(athletes)}",
                        "Last Entry": _fmt_date(et_last, today),
                    })
                st.dataframe(rows, hide_index=True, use_container_width=True)
            else:
                st.caption("No entry types set up for this sport yet.")

            st.markdown("**Needs Attention**")
            if issues:
                names = {a["id"]: a["name"] for a in athletes}
                for aid, reasons in sorted(issues.items(), key=lambda kv: names[kv[0]]):
                    st.markdown(f"- **{names[aid]}** - {'; '.join(reasons)}")
            else:
                st.caption("Nothing to fix.")
