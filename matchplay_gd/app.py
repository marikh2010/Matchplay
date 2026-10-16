"""
Entry point. Navigation is built dynamically from the database - each
sport gets one Entry page and one Dashboard page per entry type.
"""

import streamlit as st
from functools import partial
import db
from views import homepage, data_entry, dashboard, admin, export
from style import render_theme_toggle

st.set_page_config(page_title="Matchplay Tracker", page_icon="🏆", layout="wide")

sports = db.list_sports()

sections = {
    "": [st.Page(homepage.render, title="Home", icon="🏠", default=True, url_path="home")],
}

for sport in sports:
    entry_types = db.list_entry_types(sport["id"])
    if not entry_types:
        continue
    sections[sport["name"]] = [
        st.Page(
            partial(data_entry.render, sport),
            title=f"{sport['name']} Entry",
            icon="📝",
            url_path=f"{sport['name'].lower()}-entry",
        ),
        st.Page(
            partial(dashboard.render, sport),
            title=f"{sport['name']} Dashboard",
            icon="📊",
            url_path=f"{sport['name'].lower()}-dashboard",
        ),
    ]

sections["⚙️ Manage"] = [
    st.Page(admin.render, title="Admin", icon="🛠️", url_path="admin"),
    st.Page(export.render, title="Export Data", icon="📤", url_path="export"),
]

nav = st.navigation(sections, position="top")

# Small System / Light / Dark icon switch, pinned to the navbar's top-right
# by CSS in style.py. Default is "System" (follows the device setting).
render_theme_toggle()

nav.run()
