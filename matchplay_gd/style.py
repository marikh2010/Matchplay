import base64
import os
import streamlit as st

_CSS_PATH = os.path.join(os.path.dirname(__file__), "style.css")
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "isn-logo.png")

LIGHT_COLORS = {
    "bg": "#F3F5F8",
    "panel": "#FBFCFE",
    "line": "#D7DFEA",
    "text": "#1E2A39",
    "muted": "#5C6878",
    "win": "#3A9A6B",
    "lose": "#C75E57",
    "amber": "#D4A64A",
    "sky": "#6E8EAD",
    "blue": "#2F5C7B",
    "blue_light": "#A6B7C9",
}


DARK_COLORS = {
    "bg": "#1B2236",        # deep navy - page background
    "panel": "#2B3550",     # Arctic navy - cards / inputs
    "line": "#414C6C",      # navy, lifted - borders & dividers
    "text": "#E6EAEC",      # mist, lightened - body text
    "muted": "#A6A3AA",     # lavender grey - secondary text
    "win": "#86C4A2",
    "lose": "#DE9090",
    "amber": "#DCC27E",
    "sky": "#A8B8BF",       # ice blue - secondary series
    "blue": "#C3C9CC",      # mist - primary series
    "blue_light": "#A6A3AA",  # lavender grey - tertiary series
}

# In dark mode the navy sport brands would disappear into the navy
# surfaces, so chrome (active nav, primary buttons, focus) uses ice blue.
DARK_BRAND = "#A8B8BF"
DARK_BRAND_GRADIENT = "linear-gradient(135deg, #A8B8BF, #C3C9CC)"

# Python-side palette (Plotly marker colours etc.). apply_style() swaps its
# contents in place, so modules that imported COLORS see the active theme.
# Plot colours are intentionally pinned to the light palette so dashboard
# charts stay consistent regardless of the selected card theme.
COLORS = LIGHT_COLORS.copy()
PLOT_COLORS = LIGHT_COLORS.copy()
PLOT_COLORS["blue"] = "#789BB8"


SPORT_THEMES = {
    "Squash": "#1F4E79",
    "Long Jump": "#28527F",
    "Judo": "#23466E",
}
DEFAULT_BRAND = "#1F4E79"

CHART_LAYOUT = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=COLORS["text"])


def get_brand_color(sport_name: str = None) -> str:
    return SPORT_THEMES.get(sport_name, DEFAULT_BRAND)


def get_brand_ink(brand_hex: str) -> str:
    """Dark text reads fine on a bright brand color, but not on a mid-tone
    one - pick ink color by perceived brightness rather than hardcoding one
    across every sport."""
    r, g, b = int(brand_hex[1:3], 16), int(brand_hex[3:5], 16), int(brand_hex[5:7], 16)
    brightness = 0.299 * r + 0.587 * g + 0.114 * b
    return "#04121f" if brightness > 140 else "#F8F9FB"


def _hex_to_rgb_str(hex_color: str) -> str:
    """'#54C9CC' -> '84, 201, 204' - lets CSS build rgba() glows in the
    brand color, since a bare hex var can't be used inside rgba() directly."""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"{r}, {g}, {b}"


_METRIC_CARD_CYCLE_KEYS = ["blue", "sky", "blue_light", "blue"]
_STATUS_TO_COLOR_KEY = {"good": "win", "warning": "amber", "bad": "lose"}


def render_metric_row(items, colors_dict=None):
    """Renders a row of lightly tinted colored metric cards (label, value,
    optional delta/caption), using the app's own palette rather than
    st.metric() - which can't have each card individually colored via CSS,
    since every metric on the page shares one selector.

    Colours are CSS variables (--c-<key> / --c-<key>-rgb), so cards follow
    the active theme - including "System", which switches in the browser.
    colors_dict is accepted for backwards compatibility and not needed.

    items: list of dicts with keys:
      label, value, delta (optional), caption (optional)
      status (optional: "good"/"warning"/"bad") - when given, the card is
        colored to match that meaning directly (win/amber/lose) instead of
        just cycling through the palette by position.
    Cards with no status cycle through the palette in order, for plain
    informational counts that have no inherent "good or bad" meaning.
    """
    cols = st.columns(len(items), gap="large")
    cycle_i = 0
    for col, item in zip(cols, items):
        if item.get("status") in _STATUS_TO_COLOR_KEY:
            color_key = _STATUS_TO_COLOR_KEY[item["status"]]
        else:
            color_key = _METRIC_CARD_CYCLE_KEYS[cycle_i % len(_METRIC_CARD_CYCLE_KEYS)]
            cycle_i += 1
        delta_html = ""
        if item.get("delta"):
            delta_html = f"<div style='margin-top:10px;font-size:13px;opacity:0.85;'>{item['delta']}</div>"
        caption_html = ""
        if item.get("caption"):
            caption_html = f"<div style='margin-top:4px;font-size:12px;opacity:0.75;'>{item['caption']}</div>"
        with col:
            card_html = (
                f"<div style='background:rgba(var(--c-{color_key}-rgb),0.2);color:var(--text);"
                f"border:2px solid var(--c-{color_key});"
                f"border-radius:20px;margin:12px 0 24px;padding:20px 20px 18px;"
                f"box-shadow:var(--shadow-card);min-height:118px;"
                f"text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:center;'>"
                f"<div style='font-size:13px;opacity:0.85;margin-bottom:8px;'>{item['label']}</div>"
                f"<div style='font-size:28px;font-weight:700;line-height:1.1;'>{item['value']}</div>"
                f"{delta_html}{caption_html}"
                f"</div>"
            )
            st.markdown(card_html, unsafe_allow_html=True)


# =====================================================================
# Theme
# =====================================================================
# Streamlit's own System / Light / Dark picker (toolbar menu) is the single
# source of truth: it switches Streamlit's native widgets (tables, radios,
# menus, charts) and the app's CSS follows it. A separate app-level toggle
# could only repaint over Streamlit with CSS, so anything the CSS missed
# (e.g. st.dataframe, drawn on a canvas) kept the other theme.

# Streamlit sets `color-scheme` on the app root to match its active theme.
# Mirror it onto <html data-st-theme="..."> so the CSS variables (and popups
# rendered outside the app root) switch the moment the theme changes.
_THEME_SYNC_JS = """
<script>
(() => {
  if (window.__stThemeSync) return;
  window.__stThemeSync = true;
  const sync = () => {
    const app = document.querySelector('[data-testid="stApp"]');
    if (!app) return;
    const scheme = getComputedStyle(app).colorScheme.includes("dark") ? "dark" : "light";
    if (document.documentElement.dataset.stTheme !== scheme) document.documentElement.dataset.stTheme = scheme;
  };
  sync();
  setInterval(sync, 250);
})();
</script>
"""


def sync_theme():
    """Call once in app.py, before nav.run()."""
    with st.container(key="theme_sync"):
        st.html(_THEME_SYNC_JS, unsafe_allow_javascript=True)


def _is_dark() -> bool:
    """Best guess for Python-side colours; CSS follows the real theme regardless."""
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def _vars(palette: dict, brand: str, dark: bool) -> str:
    """CSS custom properties for one palette."""
    lines = [
        f"--bg: {palette['bg']};", f"--bg-2: {palette['panel']};", f"--panel: {palette['panel']};",
        f"--panel-2: {palette['bg']};", f"--line: {palette['line']};", f"--text: {palette['text']};",
        f"--muted: {palette['muted']};", f"--muted-2: {palette['muted']};",
        f"--lime: {palette['win']};", f"--lime-dim: {palette['win']};",
        f"--coral: {palette['lose']};", f"--coral-dim: {palette['lose']};",
        f"--amber: {palette['amber']};", f"--sky: {palette['sky']};",
        f"--brand: {brand};", f"--brand-ink: {get_brand_ink(brand)};", f"--brand-rgb: {_hex_to_rgb_str(brand)};",
        f"--heading: {'#F2F4F5' if dark else '#000000'};",
        f"--brand-gradient: {DARK_BRAND_GRADIENT if dark else 'linear-gradient(135deg, var(--brand), var(--sky))'};",
        f"--grid: {'rgba(168, 184, 191, 0.16)' if dark else 'rgba(21, 34, 56, 0.08)'};",
        f"--zeroline: {'rgba(168, 184, 191, 0.30)' if dark else 'rgba(21, 34, 56, 0.18)'};",
        "--shadow-card: " + ("0 6px 20px rgba(5, 9, 20, 0.45), 0 1px 3px rgba(0, 0, 0, 0.30);" if dark else
                             "0 6px 20px rgba(var(--brand-rgb), 0.15), 0 1px 3px rgba(0, 0, 0, 0.12);"),
        "--shadow-card-hover: " + ("0 10px 28px rgba(168, 184, 191, 0.18), 0 2px 5px rgba(0, 0, 0, 0.35);" if dark else
                                   "0 10px 28px rgba(var(--brand-rgb), 0.25), 0 2px 5px rgba(0, 0, 0, 0.14);"),
    ]
    for key in ("win", "lose", "amber", "sky", "blue", "blue_light", "muted"):
        lines.append(f"--c-{key}: {palette[key]}; --c-{key}-rgb: {_hex_to_rgb_str(palette[key])};")
    return "\n".join(lines)


# Rules that work in every theme because they only use the variables
# above. They override Streamlit's native widget colours, which otherwise
# follow Streamlit's own theme and could clash with a forced Light/Dark.
_THEMED_CSS = """
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] { background-color: var(--bg) !important; color: var(--text); }
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stWidgetLabel"] p, [data-testid="stExpander"] summary p, [data-testid="stRadio"] label p,
[data-testid="stCheckbox"] label p, [data-testid="stMetricValue"] { color: var(--text) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--muted) !important; }
[data-testid="stHeader"] a, [data-testid="stHeader"] span, [data-testid="stSidebarNav"] a { color: var(--text) !important; }
/* Bordered containers: older Streamlit wraps them in stVerticalBlockBorderWrapper
   (covered by style.css); newer versions render stLayoutWrapper > stVerticalBlock. */
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][data-test-scroll-behavior] {
    background-color: var(--panel) !important; border-color: var(--line) !important; box-shadow: var(--shadow-card);
}
/* Inputs */
input, textarea, [data-baseweb="select"] div, [data-baseweb="input"] input { color: var(--text) !important; }
input::placeholder, textarea::placeholder { color: var(--muted) !important; opacity: 1; }
[data-testid="stDateInput"] [role="spinbutton"], [data-testid="stDateInput"] input[type="date"] {
    color: var(--text) !important;
}
[data-testid="stDateInput"] [role="group"] > span:not([role="spinbutton"]) {
    color: var(--muted) !important;
}
[data-testid="stDateInputCalendar"], [data-testid="stDateInputCalendar"] [role="grid"],
[data-testid="stDateInputCalendar"] table {
    background-color: var(--panel) !important;
    color: var(--text) !important;
    border-color: var(--line) !important;
}
[data-testid="stDateInputCalendar"] * {
    color: var(--text) !important;
}
[data-testid="stDateInputCalendar"] [aria-disabled="true"] {
    color: var(--muted) !important;
}
[data-testid="stDateInputCalendar"] [aria-selected="true"] {
    background-color: var(--brand) !important;
    color: var(--brand-ink) !important;
}
/* Time input (segmented HH:mm:ss) - Streamlit colours the segments with its
   own theme's text at 60%, which vanishes on a light field under a dark OS. */
[data-testid="stTimeInput"] [role="spinbutton"] { color: var(--text) !important; }
[data-testid="stTimeInput"] [data-placeholder="true"],
[data-testid="stTimeInput"] [data-type="literal"] { color: var(--muted) !important; }
/* Radio: outer circle + inner dot. Unselected = muted ring, selected = soft sky blue.
   Matched by shape (a circle holding an empty dot), not nesting depth, because
   Streamlit 1.66 added a wrapper level that the old depth-based selector missed. */
[data-testid="stRadioOption"] div:has(> div:empty) { background-color: var(--muted) !important; border-color: var(--muted) !important; }
[data-testid="stRadioOption"] div:has(> div:empty) > div:empty { background-color: var(--panel) !important; }
[data-testid="stRadioOption"][data-selected="true"] div:has(> div:empty) { background-color: var(--sky) !important; border-color: var(--sky) !important; }
[data-testid="stRadioOption"][data-selected="true"] div:has(> div:empty) > div:empty { background-color: var(--panel) !important; }
/* Checkbox box (no child div) and toggle track (knob is its child div). */
[data-testid="stCheckbox"] label > span + div:not(:has(> div)) {
    background-color: var(--panel) !important; border-color: var(--muted) !important;
}
[data-testid="stCheckbox"] label[data-selected="true"] > span + div:not(:has(> div)) {
    background-color: var(--brand) !important; border-color: var(--brand) !important;
}
[data-testid="stCheckbox"] label > span + div svg, [data-testid="stCheckbox"] label > span + div polyline { stroke: var(--brand-ink) !important; }
[data-testid="stCheckbox"] label > span + div:has(> div) { background-color: var(--muted) !important; }
[data-testid="stCheckbox"] label > span + div:has(> div) > div { background-color: var(--panel) !important; }
[data-testid="stCheckbox"] label[data-selected="true"] > span + div:has(> div) { background-color: var(--brand) !important; }
[data-testid="stCheckbox"] label[data-selected="true"] > span + div:has(> div) > div { background-color: var(--brand-ink) !important; }
[data-testid="stNumberInput"] div, [data-testid="stDateInput"] div, [data-testid="stTextInput"] div,
[data-testid="stTextArea"] div, [data-testid="stTimeInput"] div, [data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div { background-color: var(--panel) !important; border-color: var(--line) !important; }
[data-baseweb="select"] > div { border-color: var(--line) !important; }
[data-baseweb="select"] > div * { background-color: transparent !important; }
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] * { background-color: transparent !important; }
[data-testid="stNumberInputStepUp"] svg, [data-testid="stNumberInputStepDown"] svg { fill: var(--text) !important; }
[data-testid="stNumberInput"] button:hover { background-color: var(--line) !important; }
[data-baseweb="popover"], [data-baseweb="popover"] > div, [data-baseweb="menu"],
[role="menu"], [role="listbox"], [data-testid="stTopNavPopoverBody"] {
    background-color: var(--panel) !important;
    color: var(--text) !important;
    border-color: var(--line) !important;
}
[data-testid="stPopoverBody"] {
    background-color: var(--panel) !important;
    color: var(--text) !important;
    border-color: var(--line) !important;
}
[data-testid="stPopoverBody"] [data-testid="stWidgetLabel"] *,
[data-testid="stPopoverBody"] [data-testid="stRadio"] label,
[data-testid="stPopoverBody"] [data-testid="stRadio"] label p,
[data-testid="stPopoverBody"] [data-testid="stCaptionContainer"] p {
    color: var(--text) !important;
}
[data-testid="stPopoverButton"], [data-testid="stPopoverButton"] button,
[data-testid="stPopover"], [data-testid="stPopover"] > div,
[data-testid="stPopover"] > button, [data-testid="stPopover"] button,
[data-testid="stPopoverButton"], [data-testid="stPopoverButton"] button {
    background-color: var(--panel) !important;
    color: var(--text) !important;
    border: 1px solid var(--line) !important;
}
[data-testid="stPopover"] *, [data-testid="stPopoverButton"] * {
    color: var(--text) !important;
}
[data-testid="stPopover"]:hover, [data-testid="stPopover"] button:hover,
[data-testid="stPopoverButton"]:hover, [data-testid="stPopoverButton"] button:hover {
    background-color: var(--line) !important;
    color: var(--text) !important;
    border-color: var(--brand) !important;
}
[data-testid="stTable"] table,
[data-testid="stTable"] th,
[data-testid="stTable"] td {
    background-color: var(--panel) !important;
    color: var(--text) !important;
    border-color: var(--line) !important;
}
[data-testid="stTable"] thead th {
    background-color: var(--panel-2) !important;
    color: var(--muted) !important;
}
button[data-testid$="FormSubmit"], [data-testid="stFormSubmitButton"] button {
    background-color: var(--panel) !important;
    color: var(--text) !important;
    border: 1px solid var(--line) !important;
}
button[data-testid$="FormSubmit"]:hover, [data-testid="stFormSubmitButton"] button:hover {
    background-color: var(--line) !important;
    color: var(--text) !important;
    border-color: var(--brand) !important;
}
[data-testid="stTopNavPopoverBody"] [data-testid="stTopNavDropdownLink"] {
    background-color: transparent !important;
    color: var(--text) !important;
}
[data-testid="stTopNavPopoverBody"] [data-testid="stTopNavDropdownLink"]:hover,
[data-testid="stTopNavPopoverBody"] [data-testid="stTopNavDropdownLink"][aria-current="page"] {
    background-color: var(--line) !important;
    color: var(--text) !important;
}
[role="menu"], [role="listbox"] {
    background-color: var(--panel) !important; color: var(--text) !important; border-color: var(--line) !important;
}
[role="listbox"] [role="option"] {
    color: var(--text) !important;
}
[role="listbox"] [role="option"]:hover,
[role="listbox"] [role="option"][aria-selected="true"] {
    background-color: var(--line) !important;
    color: var(--text) !important;
}
[data-baseweb="popover"] ul, [data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"] { background-color: var(--panel) !important; }
[data-baseweb="popover"] [role="menuitem"], [data-baseweb="menu"] [role="menuitem"], [role="menu"] [role="menuitem"] {
    color: var(--text) !important;
}
[data-baseweb="popover"] [role="menuitem"]:hover, [data-baseweb="menu"] [role="menuitem"]:hover,
[role="menu"] [role="menuitem"]:hover { background-color: var(--line) !important; }
[data-baseweb="popover"] li, [data-baseweb="popover"] [role="option"] { color: var(--text) !important; }
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] [aria-selected="true"] { background-color: var(--line) !important; }
[data-baseweb="tag"] { background-color: var(--line) !important; color: var(--text) !important; }
[data-testid="stExpander"] details, [data-testid="stExpander"] summary { background-color: var(--panel) !important; border-color: var(--line) !important; }
.stDownloadButton > button { background-color: var(--panel); color: var(--text); border: 1px solid var(--line); }
.stDownloadButton > button:hover { border-color: var(--brand); color: var(--brand); }
/* Plotly: Streamlit's chart theme follows Streamlit's theme, not ours. */
.js-plotly-plot .gtitle, .js-plotly-plot .legendtext { fill: var(--text) !important; }
.js-plotly-plot .xtick text, .js-plotly-plot .ytick text,
.js-plotly-plot .g-xtitle text, .js-plotly-plot .g-ytitle text { fill: var(--text) !important; }
.js-plotly-plot .xaxislayer-above text, .js-plotly-plot .xaxislayer-below text,
.js-plotly-plot .yaxislayer-above text, .js-plotly-plot .yaxislayer-below text {
    fill: var(--text) !important;
    opacity: 1 !important;
}
.js-plotly-plot .xaxislayer-above path, .js-plotly-plot .yaxislayer-above path,
.js-plotly-plot .xaxislayer-below path, .js-plotly-plot .yaxislayer-below path { stroke: var(--text) !important; }
.js-plotly-plot .gridlayer path { stroke: var(--grid) !important; }
.js-plotly-plot .zerolinelayer path { stroke: var(--zeroline) !important; }
.js-plotly-plot .bg { fill: transparent !important; }
.modebar-btn path { fill: var(--muted) !important; }

/* Secondary (right-hand) y-axis labels and titles, e.g. Avg HR on dual-axis charts. */
.js-plotly-plot [class*="y2tick"] text, .js-plotly-plot [class*="g-y2title"] text { fill: var(--text) !important; opacity: 1 !important; }
/* The theme-sync script's container takes no space. */
.st-key-theme_sync { display: none !important; }
/* Icons that take the base theme's colour (nav chevrons, select arrows) */
[data-testid="stHeader"] svg, [data-baseweb="select"] svg, [data-testid="stSelectbox"] svg,
[data-testid="stMultiSelect"] svg, [data-testid="stExpander"] summary svg {
    color: var(--text) !important; fill: currentColor;
}
"""

# Dark-only rules (Streamlit's light alerts / code blocks are too bright).
# {root} is filled in with the selector that means "dark is active".
_DARK_ONLY_CSS = """
{root} [data-testid="stAlert"] {{ background-color: rgba(168, 184, 191, 0.12) !important; }}
{root} [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {{ color: var(--text) !important; }}
{root} code {{ background-color: var(--bg) !important; color: var(--text) !important; }}
{root} [data-testid="stDateInput"] input[type="date"] {{ color-scheme: dark; }}
"""

_LIGHT_ONLY_CSS = """
[data-testid="stDateInput"] input[type="date"] { color-scheme: light; }
"""


def apply_style(sport_name: str = None):
    """Call after the page knows which sport is selected (or with None for
    a sport-agnostic page). Safe to call more than once per page."""
    if sport_name:
        st.session_state["selected_sport_name"] = sport_name

    dark = _is_dark()

    # Cards follow the active theme, but dashboard graphs intentionally stay on
    # the light-mode series palette so they remain visually consistent.
    COLORS.clear()
    COLORS.update(DARK_COLORS if dark else LIGHT_COLORS)
    PLOT_COLORS.clear()
    PLOT_COLORS.update(LIGHT_COLORS)
    PLOT_COLORS["blue"] = "#789BB8"
    CHART_LAYOUT.update(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=COLORS["text"],
    )

    light_brand = get_brand_color(sport_name or st.session_state.get("selected_sport_name"))
    light_vars = _vars(LIGHT_COLORS, light_brand, dark=False)
    dark_vars = _vars(DARK_COLORS, DARK_BRAND, dark=True)

    # Light by default; dark when the sync script reports Streamlit is dark.
    # Until the script has run, fall back to the device setting (which is
    # also what Streamlit's default "System" theme follows).
    os_dark = ':root:not([data-st-theme="light"])'
    st_dark = ':root[data-st-theme="dark"]'
    theme_css = (f":root {{ {light_vars} }}\n{_LIGHT_ONLY_CSS}\n"
                 f"@media (prefers-color-scheme: dark) {{ {os_dark} {{ {dark_vars} }}\n{_DARK_ONLY_CSS.format(root=os_dark)} }}\n"
                 f"{st_dark} {{ {dark_vars} }}\n{_DARK_ONLY_CSS.format(root=st_dark)}")

    with open(_CSS_PATH) as f:
        css = f.read()
    with open(_LOGO_PATH, "rb") as logo_file:
        logo_data = base64.b64encode(logo_file.read()).decode("ascii")
    logo_css = f"""
[data-testid="stMarkdownContainer"] h1::before {{
    content: ""; display: inline-block; vertical-align: middle;
    width: 118px; height: 77px; margin-right: 12px;
    background: center / contain no-repeat url("data:image/png;base64,{logo_data}");
}}
"""
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    st.markdown(f"<style>{theme_css}\n{_THEMED_CSS}\n{logo_css}</style>", unsafe_allow_html=True)
