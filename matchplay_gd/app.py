"""
Entry point. Navigation is built dynamically from the database - each
sport gets one Entry page and one Dashboard page per entry type.
"""

import streamlit as st
from functools import partial
import db
from views import homepage, data_entry, dashboard, admin, export
from style import sync_theme

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

# Light / dark is chosen in Streamlit's own toolbar menu (default "System",
# following the device). This keeps the app's CSS in step with it.
sync_theme()

nav.run()
