import streamlit as st
import db
from style import apply_style
from dashboards import matchplay, rsa, yoyo, longjump, judo

_DASHBOARDS = {
    "Match Play": matchplay,
    "RSA Test": rsa,
    "Yo-Yo Intermittent Recovery Level 1 & Blood Lactate Test": yoyo,
    "Long Jump Test": longjump,
    "Judo Fitness Test": judo,
}


def render(sport):
    apply_style(sport["name"])
    st.title(f"{sport['name']} Dashboard")

    entry_types = db.list_entry_types(sport["id"])
    if not entry_types:
        st.info("No entry types set up for this sport yet.")
        st.stop()

    if len(entry_types) > 1:
        et_name = st.selectbox("View", [et["name"] for et in entry_types])
        entry_type = next(et for et in entry_types if et["name"] == et_name)
    else:
        entry_type = entry_types[0]

    module = _DASHBOARDS.get(entry_type["name"])
    if module is None:
        st.info(f"No dashboard built for '{entry_type['name']}' yet.")
        return
    module.render(sport, entry_type)
