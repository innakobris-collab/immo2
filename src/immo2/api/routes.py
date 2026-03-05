"""
API routes for immo2 MVP.
POST /analyze     → run full pipeline, return AnalysisReport JSON
GET  /report/{id} → download PDF
"""
from __future__ import annotations
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel

from ..models.listing import RawListing
from ..models.financials import FinancingParams
from ..agents.pipeline import run_analysis
from ..reporting.pdf_generator import generate_pdf

router = APIRouter()

# In-memory report store (MVP only — replace with DB in V1)
_reports: dict[str, object] = {}


class AnalyzeTextRequest(BaseModel):
    text: str
    source_url: str | None = None
    eigenkapital_pct: float = 20.0
    finanzierungszins: float = 3.5
    tilgung_pct: float = 2.0
    renovation_eur: float = 0.0
    marginal_tax_rate: float = 0.42


@router.post("/analyze/text")
async def analyze_text(req: AnalyzeTextRequest):
    """Analyze a listing from raw text (manual entry or pre-extracted)."""
    raw = RawListing(
        raw_text=req.text,
        source_url=req.source_url,
        source_type="manual",
    )
    params = FinancingParams(
        eigenkapital_pct=req.eigenkapital_pct,
        finanzierungszins=req.finanzierungszins,
        tilgung_pct=req.tilgung_pct,
    )
    report = await run_analysis(
        raw_listing=raw,
        financing_params=params,
        renovation_plan_eur=req.renovation_eur,
        marginal_tax_rate=req.marginal_tax_rate,
    )
    _reports[report.job_id] = report
    return report


@router.post("/analyze/pdf")
async def analyze_pdf(
    file: Annotated[UploadFile, File(description="Exposé PDF")],
    eigenkapital_pct: Annotated[float, Form()] = 20.0,
    finanzierungszins: Annotated[float, Form()] = 3.5,
    tilgung_pct: Annotated[float, Form()] = 2.0,
    renovation_eur: Annotated[float, Form()] = 0.0,
    marginal_tax_rate: Annotated[float, Form()] = 0.42,
):
    """Analyze a listing from an uploaded PDF exposé."""
    from ..intake.pdf_extract import extract_from_pdf

    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    pdf_bytes = await file.read()
    raw = extract_from_pdf(pdf_bytes)

    params = FinancingParams(
        eigenkapital_pct=eigenkapital_pct,
        finanzierungszins=finanzierungszins,
        tilgung_pct=tilgung_pct,
    )
    report = await run_analysis(
        raw_listing=raw,
        financing_params=params,
        renovation_plan_eur=renovation_eur,
        marginal_tax_rate=marginal_tax_rate,
    )
    _reports[report.job_id] = report
    return report


@router.get("/report/{job_id}/pdf")
async def download_pdf(job_id: str):
    """Download the PDF report for a completed analysis."""
    report = _reports.get(job_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {job_id} not found")

    pdf_bytes = await generate_pdf(report)
    filename = f"immo2_{report.listing.plz or job_id}_{report.listing.stadt or ''}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report/{job_id}")
async def get_report(job_id: str):
    """Get report JSON for a completed analysis."""
    report = _reports.get(job_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {job_id} not found")
    return report
