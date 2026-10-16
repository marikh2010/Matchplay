import datetime
import base64
from copy import deepcopy
import io
import os
import streamlit as st
from fpdf import FPDF, XPos, YPos

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "isn-logo.png")
_REPORT_TEXT = "#1E2A39"
_REPORT_GRID = "#D7DFEA"


def _light_figure(fig):
    light_fig = deepcopy(fig)
    light_fig.update_layout(
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font_color=_REPORT_TEXT,
        hoverlabel=dict(bgcolor="#FFFFFF", font_color=_REPORT_TEXT),
    )
    axis_style = {
        "color": _REPORT_TEXT,
        "linecolor": _REPORT_TEXT,
        "tickfont": {"color": _REPORT_TEXT},
        "title": {"font": {"color": _REPORT_TEXT}},
        "gridcolor": _REPORT_GRID,
        "zerolinecolor": _REPORT_GRID,
    }
    light_fig.update_xaxes(**axis_style)
    light_fig.update_yaxes(**axis_style)
    return light_fig


class ReportBuilder:
    def __init__(self, title: str, brand_color: str = "#2563EB"):
        self.title = title
        self.brand = brand_color
        self.sections = []
        self.remarks = None

    def heading(self, text: str):
        self.sections.append(("heading", text))

    def metrics(self, items):
        """items: list of (label, value) tuples."""
        self.sections.append(("metrics", items))

    def chart(self, title: str, fig):
        self.sections.append(("chart", (title, fig)))

    def insight(self, text: str):
        self.sections.append(("insight", text))

    def table(self, title: str, rows: list):
        self.sections.append(("table", (title, rows)))

    def set_remarks(self, text: str):
        self.remarks = text.strip() if text and text.strip() else None

    def merge(self, other: "ReportBuilder", section_heading: str = None):
        """Append another ReportBuilder's sections into this one - used to
        combine several athletes' individual reports into one export."""
        if section_heading:
            self.heading(section_heading)
        self.sections.extend(other.sections)

    # ---------- HTML ----------
    def _build_html(self) -> str:
        with open(_LOGO_PATH, "rb") as logo_file:
            logo_data = base64.b64encode(logo_file.read()).decode("ascii")
        logo_src = f"data:image/png;base64,{logo_data}"
        head = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>{self.title}</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body {{ margin:0; background:#FFFFFF; color:#1A1D29; font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif; padding:24px 20px 60px; }}
  .wrap {{ max-width:1000px; margin:0 auto; }}
    .report-header {{ display:flex; align-items:center; gap:16px; margin-bottom:2px; }}
    .report-logo {{ width:100px; max-height:68px; object-fit:contain; flex:none; }}
    h1 {{ color:{self.brand}; margin:0; }}
  h2 {{ color:{self.brand}; border-top:1px solid #E2E5EA; padding-top:16px; margin-top:26px; font-size:18px; }}
  h3 {{ font-size:13.5px; margin:14px 0 6px; color:#1A1D29; }}
  .meta {{ color:#6B7280; font-size:12.5px; margin-bottom:18px; }}
  .remarks {{ background:#F8F9FB; border:1px solid #E2E5EA; border-radius:12px; padding:14px 16px; margin-bottom:18px; font-size:13.5px; white-space:pre-wrap; }}
  .metrics-row {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }}
  .metric {{ background:#F8F9FB; border:1px solid #E2E5EA; border-top:3px solid {self.brand}; border-radius:12px; padding:10px 14px; min-width:140px; }}
  .metric .label {{ color:#6B7280; font-size:11.5px; margin-bottom:3px; }}
  .metric .value {{ font-size:19px; font-weight:700; }}
  .insight {{ background:#F8F9FB; border-left:3px solid {self.brand}; border-radius:8px; padding:9px 14px; margin-bottom:8px; font-size:13px; color:#3A3448; line-height:1.5; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; margin-bottom:14px; }}
  th, td {{ padding:6px 10px; border-bottom:1px solid #E2E5EA; text-align:left; }}
  th {{ color:#6B7280; font-size:11px; text-transform:uppercase; }}
</style></head><body><div class="wrap">
<header class="report-header"><img class="report-logo" src="{logo_src}" alt="ISN logo"><h1>{self.title}</h1></header>
<div class="meta">Exported {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
"""
        remarks_html = f"<div class='remarks'><b>Remarks</b><br>{self.remarks}</div>" if self.remarks else ""
        body = ""
        for i, (kind, payload) in enumerate(self.sections):
            if kind == "heading":
                body += f"<h2>{payload}</h2>"
            elif kind == "metrics":
                row = "".join(f"<div class='metric'><div class='label'>{lbl}</div><div class='value'>{val}</div></div>" for lbl, val in payload)
                body += f"<div class='metrics-row'>{row}</div>"
            elif kind == "chart":
                title, fig = payload
                chart_html = _light_figure(fig).to_html(full_html=False, include_plotlyjs=False, div_id=f"chart_{i}")
                body += f"<h3>{title}</h3>{chart_html}"
            elif kind == "insight":
                body += f"<div class='insight'>{payload}</div>"
            elif kind == "table":
                title, rows = payload
                if rows:
                    cols = list(rows[0].keys())
                    thead = "".join(f"<th>{c}</th>" for c in cols)
                    trows = "".join("<tr>" + "".join(f"<td>{r.get(c, '')}</td>" for c in cols) + "</tr>" for r in rows)
                    body += f"<h3>{title}</h3><table><tr>{thead}</tr>{trows}</table>"
        return head + remarks_html + body + "</div></body></html>"

    # ---------- PDF (charts embedded as static images) ----------
    def _build_pdf(self) -> bytes:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 18)
        pdf.image(_LOGO_PATH, x=10, y=10, h=16)
        pdf.set_xy(40, 10)
        pdf.multi_cell(0, 10, self.title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 6, f"Exported {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        if self.remarks:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(26, 29, 41)
            pdf.cell(0, 7, "Remarks", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, self.remarks, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(3)

        for kind, payload in self.sections:
            if pdf.get_y() > 260:
                pdf.add_page()
            if kind == "heading":
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(26, 29, 41)
                pdf.ln(2)
                pdf.cell(0, 8, payload, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif kind == "metrics":
                pdf.set_font("Helvetica", "", 10)
                for lbl, val in payload:
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(60, 6, str(lbl))
                    pdf.set_text_color(26, 29, 41)
                    pdf.cell(0, 6, str(val), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(2)
            elif kind == "chart":
                title, fig = payload
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(26, 29, 41)
                pdf.cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                try:
                    png_bytes = _light_figure(fig).to_image(format="png", width=900, height=430, scale=2)
                    if pdf.get_y() > 190:
                        pdf.add_page()
                    pdf.image(io.BytesIO(png_bytes), w=180)
                    pdf.ln(3)
                except Exception:
                    pdf.set_font("Helvetica", "I", 9)
                    pdf.set_text_color(107, 114, 128)
                    pdf.multi_cell(0, 6, "(Chart image unavailable in this environment - see the HTML export for the visual version.)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.ln(1)
            elif kind == "insight":
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(26, 29, 41)
                pdf.multi_cell(0, 6, str(payload).replace("**", ""), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1)
            elif kind == "table":
                title, rows = payload
                if not rows:
                    continue
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(26, 29, 41)
                pdf.cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                cols = list(rows[0].keys())
                col_w = 190 / len(cols)
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_text_color(107, 114, 128)
                for c in cols:
                    pdf.cell(col_w, 6, str(c), border="B")
                pdf.ln(6)
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(26, 29, 41)
                for r in rows:
                    for c in cols:
                        pdf.cell(col_w, 6, str(r.get(c, "")), border="B")
                    pdf.ln(6)
                pdf.ln(3)
        return bytes(pdf.output())

    def render_export_controls(self, filename_base: str, key: str):
        """Remarks box + format choice + download button, all in one call."""
        remarks = st.text_area("Remarks (included in the exported report)", key=f"{key}_remarks", placeholder="Optional notes for whoever receives this report...")
        self.set_remarks(remarks)
        fmt = st.radio("Export format", ["HTML (interactive charts)", "PDF (chart images, not interactive)"], horizontal=True, key=f"{key}_fmt")
        if fmt.startswith("HTML"):
            st.download_button("\U0001F4C4 Export report", data=self._build_html(), file_name=f"{filename_base}.html", mime="text/html", key=f"{key}_dl")
        else:
            with st.spinner("Rendering chart images..."):
                pdf_bytes = self._build_pdf()
            st.download_button("\U0001F4C4 Export report", data=pdf_bytes, file_name=f"{filename_base}.pdf", mime="application/pdf", key=f"{key}_dl")

    def download_button(self, filename: str, key: str):
        """Back-compat: HTML-only, no remarks/format UI."""
        st.download_button("\U0001F4C4 Export report", data=self._build_html(), file_name=filename, mime="text/html", key=key)
