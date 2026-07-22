"""
Report Writer — the "Generate Report" button. Assembles an executive-style
report (executive summary, data quality, key findings each paired with a
chart, recommendations) from a Gemini-written narrative plus the existing
key-insights pipeline, then renders it as branded standalone HTML (dark
header, cyan accents — matching Prism's Streamlit theme) and as a PDF via
fpdf2, with charts rasterized to PNG via kaleido for the PDF.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from io import BytesIO
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF

from modules.ai_analyst import build_data_context, call_gemini, generate_key_insights

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_NARRATIVE_PROMPT_TEMPLATE = (
    "{context}\n\n"
    "Missing values by column: {missing_summary}\n"
    "Outliers by column (IQR method): {outlier_summary}\n"
    "Duplicate rows: {duplicate_rows}\n\n"
    "You are a senior data analyst writing an executive report for a business stakeholder. "
    "Based only on the information above, return a JSON object with two keys:\n"
    '- "executive_summary": a 3-4 sentence paragraph summarizing what this dataset is and its '
    "overall health, in plain English for a non-technical reader.\n"
    '- "recommendations": a list of 3-5 short, actionable recommendations (each one sentence), '
    "based on the data quality issues and patterns above.\n\n"
    "Return ONLY the JSON object, no prose, no markdown code fences."
)

BRAND_DARK = "#0a0e17"
BRAND_ACCENT = "#00e5ff"
BRAND_TEXT = "#e0f7fa"
BRAND_MUTED = "#9fb3c8"


def _default_narrative(quality_report: dict) -> dict:
    """Templated fallback narrative, built purely from quality_report's numbers."""
    summary = (
        f"This dataset contains {quality_report['n_rows']:,} rows and {quality_report['n_cols']} columns, "
        f"with {quality_report['total_missing_pct']}% missing values overall and "
        f"{quality_report['duplicate_rows']} duplicate row(s)."
    )
    recommendations = []
    if quality_report["total_missing_pct"] > 0:
        recommendations.append(
            "Address missing values in the columns with the highest missing percentage before further analysis."
        )
    if quality_report["duplicate_rows"] > 0:
        recommendations.append("Remove duplicate rows to avoid double-counting in aggregate metrics.")
    if quality_report.get("all_null_columns"):
        recommendations.append(f"Drop fully empty column(s): {', '.join(quality_report['all_null_columns'])}.")
    if not recommendations:
        recommendations.append(
            "Data quality looks solid — proceed to deeper analysis (segmentation, forecasting, or statistical testing)."
        )
    return {"executive_summary": summary, "recommendations": recommendations}


def generate_report_narrative(model, df: pd.DataFrame, quality_report: dict, column_types: dict[str, str]) -> dict:
    """Ask Gemini for an executive summary + recommendations. Always returns
    something renderable — falls back to _default_narrative() on any
    failure, bad JSON, or an incomplete response.
    """
    if model is None:
        return _default_narrative(quality_report)

    context = build_data_context(df, column_types)
    missing_summary = (
        ", ".join(f"{c}: {p}%" for c, p in quality_report["missing_by_column"].items() if p > 0) or "none"
    )
    outlier_summary = (
        ", ".join(f"{c}: {v['count']} ({v['pct']}%)" for c, v in quality_report["outliers"].items() if v["count"] > 0)
        or "none"
    )
    prompt = _NARRATIVE_PROMPT_TEMPLATE.format(
        context=context, missing_summary=missing_summary, outlier_summary=outlier_summary,
        duplicate_rows=quality_report["duplicate_rows"],
    )

    text, error = call_gemini(model, prompt)
    if error:
        return _default_narrative(quality_report)

    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return _default_narrative(quality_report)

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _default_narrative(quality_report)

    summary = parsed.get("executive_summary")
    recommendations = parsed.get("recommendations")
    if not summary or not isinstance(recommendations, list) or not recommendations:
        return _default_narrative(quality_report)
    return {"executive_summary": str(summary), "recommendations": [str(r) for r in recommendations][:5]}


def build_report_content(
    model,
    df: pd.DataFrame,
    quality_report: dict,
    column_types: dict[str, str],
    charts: dict[str, go.Figure],
    top_correlations: Optional[list[tuple[str, str, float]]] = None,
) -> dict:
    """Assemble everything the HTML/PDF renderers need: the narrative, up to
    5 key findings (reusing ai_analyst.generate_key_insights), and up to 3
    representative charts to embed alongside them.
    """
    narrative = generate_report_narrative(model, df, quality_report, column_types)
    findings, findings_error = generate_key_insights(model, df, quality_report, column_types, top_correlations)
    return {
        "executive_summary": narrative["executive_summary"],
        "recommendations": narrative["recommendations"],
        "quality_report": quality_report,
        "findings": findings,
        "findings_error": findings_error,
        "chart_items": list(charts.items())[:3],
        "n_rows": df.shape[0],
        "n_cols": df.shape[1],
    }


_HTML_CSS = f"""
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: {BRAND_DARK}; color: {BRAND_TEXT}; margin: 0; padding: 0; }}
  .header {{ background: linear-gradient(90deg, #05070d, #0d1220); border-bottom: 2px solid {BRAND_ACCENT}; padding: 2rem; }}
  .header h1 {{ color: {BRAND_ACCENT}; margin: 0; text-shadow: 0 0 12px rgba(0,229,255,0.3); }}
  .header p {{ color: {BRAND_MUTED}; margin: 0.4rem 0 0; }}
  .content {{ padding: 2rem; max-width: 900px; margin: 0 auto; }}
  h2 {{ color: {BRAND_ACCENT}; border-left: 3px solid {BRAND_ACCENT}; padding-left: 0.6rem; margin-top: 2.5rem; }}
  .card {{ background: #111827; border: 1px solid #1c2942; border-left: 3px solid {BRAND_ACCENT}; border-radius: 8px;
           padding: 1rem 1.4rem; margin-bottom: 0.8rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #26344a; padding: 6px 10px; text-align: left; font-size: 0.9rem; }}
  th {{ background: #111827; color: {BRAND_ACCENT}; }}
  tr:nth-child(even) {{ background: #0f1520; }}
  ol li, ul li {{ margin-bottom: 0.4rem; }}
  .footer {{ margin-top: 3rem; padding: 1.5rem 2rem; color: #6b7d94; font-size: 0.8rem; border-top: 1px solid #1c2942; }}
</style>
"""


def generate_html_report(report_content: dict, dataset_name: str) -> str:
    """Render report_content (from build_report_content()) as a standalone,
    Prism-branded HTML file — charts stay interactive (Plotly JS embedded).
    """
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    quality = report_content["quality_report"]

    findings_html = "".join(f'<div class="card">{finding}</div>' for finding in report_content["findings"]) or (
        f"<p>{report_content.get('findings_error') or 'No findings generated.'}</p>"
    )
    recs_html = "".join(f"<li>{r}</li>" for r in report_content["recommendations"])

    charts_html_parts = []
    for i, (title, fig) in enumerate(report_content["chart_items"]):
        include_js = "cdn" if i == 0 else False
        charts_html_parts.append(f"<h3>{title}</h3>{fig.to_html(full_html=False, include_plotlyjs=include_js)}")
    charts_html = "".join(charts_html_parts)

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Prism — Analysis Report</title>
  {_HTML_CSS}
</head>
<body>
  <div class="header">
    <h1>PRISM — Analysis Report</h1>
    <p>{dataset_name} &middot; Generated {generated_at} &middot; {report_content['n_rows']:,} rows &times; {report_content['n_cols']} columns</p>
  </div>
  <div class="content">
    <h2>Executive Summary</h2>
    <p>{report_content['executive_summary']}</p>

    <h2>Data Quality</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Rows</td><td>{quality['n_rows']:,}</td></tr>
      <tr><td>Columns</td><td>{quality['n_cols']}</td></tr>
      <tr><td>Missing (overall)</td><td>{quality['total_missing_pct']}%</td></tr>
      <tr><td>Duplicate Rows</td><td>{quality['duplicate_rows']}</td></tr>
      <tr><td>Memory Usage</td><td>{quality['memory_usage']}</td></tr>
    </table>

    <h2>Key Findings</h2>
    {findings_html}
    {charts_html}

    <h2>Recommendations</h2>
    <ol>{recs_html}</ol>
  </div>
  <div class="footer">Generated by Prism — an Auto-EDA tool with an AI analyst layer. Developed by Prathmesh Katkade.</div>
</body>
</html>"""


# fpdf2's core fonts only support latin-1 — Gemini's output often contains
# smart quotes/dashes, so map the common ones to ASCII before falling back
# to a lossy latin-1 encode as a last resort (never raise on odd Unicode).
_PDF_CHAR_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "•": "-",
    "₹": "Rs.", "−": "-",
}


def _sanitize_for_pdf(text: str) -> str:
    for src, dst in _PDF_CHAR_MAP.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


class _ReportPDF(FPDF):
    def header(self) -> None:
        self.set_fill_color(10, 14, 23)
        self.rect(0, 0, self.w, 20, style="F")
        self.set_text_color(0, 229, 255)
        self.set_font("Helvetica", "B", 15)
        self.set_xy(10, 5)
        self.cell(0, 10, "PRISM - Analysis Report")
        self.set_text_color(0, 0, 0)
        self.ln(18)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 130, 145)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def _add_section_title(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(0, 150, 180)
    pdf.cell(0, 10, _sanitize_for_pdf(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(20, 20, 20)
    pdf.set_font("Helvetica", "", 11)


def generate_pdf_report(report_content: dict, dataset_name: str) -> bytes:
    """Render the same report content as a downloadable PDF via fpdf2, with
    charts rasterized to PNG via kaleido (fpdf2 can't embed interactive charts).
    """
    pdf = _ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 110, 125)
    pdf.cell(
        0, 8,
        _sanitize_for_pdf(
            f"{dataset_name} | Generated {generated_at} | "
            f"{report_content['n_rows']:,} rows x {report_content['n_cols']} columns"
        ),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(20, 20, 20)
    pdf.ln(4)

    _add_section_title(pdf, "Executive Summary")
    pdf.multi_cell(0, 6, _sanitize_for_pdf(report_content["executive_summary"]), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    _add_section_title(pdf, "Data Quality")
    quality = report_content["quality_report"]
    for line in [
        f"Rows: {quality['n_rows']:,}",
        f"Columns: {quality['n_cols']}",
        f"Missing (overall): {quality['total_missing_pct']}%",
        f"Duplicate rows: {quality['duplicate_rows']}",
        f"Memory usage: {quality['memory_usage']}",
    ]:
        pdf.cell(0, 6, _sanitize_for_pdf(line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    _add_section_title(pdf, "Key Findings")
    if report_content["findings"]:
        for i, finding in enumerate(report_content["findings"], 1):
            pdf.multi_cell(0, 6, _sanitize_for_pdf(f"{i}. {finding}"), new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.multi_cell(
            0, 6, _sanitize_for_pdf(report_content.get("findings_error") or "No findings generated."),
            new_x="LMARGIN", new_y="NEXT",
        )
    pdf.ln(2)

    for title, fig in report_content["chart_items"]:
        try:
            img_bytes = fig.to_image(format="png", width=700, height=400, scale=2)
        except Exception:
            continue
        if pdf.get_y() > pdf.h - 110:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, _sanitize_for_pdf(title), new_x="LMARGIN", new_y="NEXT")
        pdf.image(BytesIO(img_bytes), w=170)
        pdf.ln(4)

    _add_section_title(pdf, "Recommendations")
    for i, rec in enumerate(report_content["recommendations"], 1):
        pdf.multi_cell(0, 6, _sanitize_for_pdf(f"{i}. {rec}"), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


# ==========================================================================
# Cleaning Certificate — a one-page audit trail (not a marketing report):
# dataset name, date, Data Health Score before/after, and every cleaning
# action taken with its outcome, in banking-audit language. Reuses the same
# fpdf2 helpers as the analysis report above, with its own header/footer.
# ==========================================================================
class _CertificatePDF(FPDF):
    def header(self) -> None:
        self.set_fill_color(10, 14, 23)
        self.rect(0, 0, self.w, 20, style="F")
        self.set_text_color(0, 229, 255)
        self.set_font("Helvetica", "B", 14)
        self.set_xy(10, 5)
        self.cell(0, 10, "PRISM - Data Cleaning Certificate")
        self.set_text_color(0, 0, 0)
        self.ln(18)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 130, 145)
        self.cell(0, 10, f"Page {self.page_no()} - Prism v5", align="C")


def generate_cleaning_certificate(
    dataset_name: str,
    n_rows: int,
    n_cols: int,
    health_before: int,
    health_after: int,
    cleaning_log: list[dict],
    developer_name: str = "Prathmesh Katkade",
) -> bytes:
    """A one-page PDF documenting exactly what was done to a dataset before
    analysis — positioned as an audit trail a compliance or banking
    reviewer could sign off on, not a promotional report. cleaning_log is
    the same list[{"description","code"}] already used for Export as
    Python Script, so this is always in sync with what actually ran.
    """
    pdf = _CertificatePDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    delta = health_after - health_before
    delta_str = f"+{delta}" if delta >= 0 else str(delta)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 110, 125)
    pdf.cell(0, 8, _sanitize_for_pdf(f"Dataset: {dataset_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, _sanitize_for_pdf(f"Generated: {generated_at}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, _sanitize_for_pdf(f"Shape: {n_rows:,} rows x {n_cols} columns"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(20, 20, 20)
    pdf.ln(4)

    _add_section_title(pdf, "Data Health Score")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _sanitize_for_pdf(f"{health_before} / 100  ->  {health_after} / 100  ({delta_str})"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(4)

    _add_section_title(pdf, f"Actions Taken ({len(cleaning_log)})")
    if cleaning_log:
        for i, step in enumerate(cleaning_log, 1):
            pdf.multi_cell(0, 6, _sanitize_for_pdf(f"{i}. {step['description']}"), new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.multi_cell(
            0, 6, "No cleaning actions were applied to this dataset.", new_x="LMARGIN", new_y="NEXT",
        )
    pdf.ln(6)

    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 110, 125)
    pdf.multi_cell(
        0, 5,
        _sanitize_for_pdf(
            "This certificate documents the automated (Auto Cleaner, safe-tier) and user-approved "
            "data cleaning operations applied to the dataset above, in the order they were run. "
            f"Prepared by {developer_name} using Prism v5."
        ),
        new_x="LMARGIN", new_y="NEXT",
    )

    return bytes(pdf.output())
