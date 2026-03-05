"""
PDF report generation using Jinja2 + Playwright sync API.
Uses playwright.sync_api — no asyncio needed, works in Streamlit and any context.
"""
from __future__ import annotations
from pathlib import Path
from ..models.report import AnalysisReport

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _build_html(report: AnalysisReport) -> str:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)
    env.filters["eur"] = lambda v: f"\u20ac{v:,.0f}" if v is not None else "\u2013"
    env.filters["pct"] = lambda v: f"{v:.2f}%" if v is not None else "\u2013"
    env.filters["sign_eur"] = lambda v: f"+\u20ac{v:,.0f}" if v >= 0 else f"\u2013\u20ac{abs(v):,.0f}"
    template = env.get_template("report.html.jinja2")
    return template.render(
        report=report, listing=report.listing,
        cashflow=report.cashflow, score=report.deal_score,
        rent=report.rent_estimate, flags=report.red_flags,
    )


def generate_pdf_sync(report: AnalysisReport) -> bytes:
    """Generate PDF using Playwright sync API. Works in Streamlit, threads, anywhere."""
    from playwright.sync_api import sync_playwright
    html_str = _build_html(report)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_str, wait_until="networkidle")
        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20mm", "right": "16mm", "bottom": "20mm", "left": "16mm"},
        )
        browser.close()
    return pdf_bytes


# Keep async version for pipeline use
async def generate_pdf(report: AnalysisReport) -> bytes:
    """Async version for use in the pipeline."""
    from playwright.async_api import async_playwright
    html_str = _build_html(report)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_str, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20mm", "right": "16mm", "bottom": "20mm", "left": "16mm"},
        )
        await browser.close()
    return pdf_bytes


def generate_html(report: AnalysisReport) -> str:
    """Return rendered HTML (useful for preview)."""
    return _build_html(report)
