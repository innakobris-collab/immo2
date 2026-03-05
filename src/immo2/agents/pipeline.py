"""
MVP pipeline: Intake → Extract → Cashflow → Report.
Sequential Python functions — no LangGraph needed at this scale.
"""
from __future__ import annotations
import uuid
from ..models.listing import RawListing, ExtractedListing
from ..models.financials import FinancingParams
from ..models.report import AnalysisReport
from .agent2_extract import extract_listing
from ..cashflow.engine import run_cashflow
from ..rag.mietspiegel_stubs import get_mietspiegel_estimate
from ..cashflow.scoring import score_deal
from loguru import logger


async def run_analysis(
    raw_listing: RawListing,
    financing_params: FinancingParams | None = None,
    rent_kalt_override: float | None = None,
    renovation_plan_eur: float = 0.0,
    marginal_tax_rate: float = 0.42,
) -> AnalysisReport:
    """Full analysis pipeline. Returns AnalysisReport."""
    job_id = str(uuid.uuid4())[:8]
    report = AnalysisReport(job_id=job_id, listing=ExtractedListing())

    # ── Step 1: Extract ──────────────────────────────────────────────────────
    logger.info(f"[{job_id}] Extracting listing data...")
    try:
        listing = await extract_listing(raw_listing)
        report.listing = listing
        report.extraction_complete = True
    except Exception as e:
        report.errors.append(f"Extraction failed: {e}")
        logger.error(f"[{job_id}] Extraction error: {e}")
        return report

    if not listing.is_ready_for_cashflow:
        missing = listing.requires_user_input
        report.errors.append(f"Missing required fields: {missing}")
        logger.warning(f"[{job_id}] Missing fields: {missing}")
        return report

    # ── Step 2: Rent estimate (Mietspiegel) ──────────────────────────────────
    logger.info(f"[{job_id}] Getting Mietspiegel rent estimate...")
    rent_estimate = get_mietspiegel_estimate(
        stadt=listing.stadt,
        baujahr=listing.baujahr,
        wohnflaeche_m2=listing.wohnflaeche_m2,
        stadtteil=listing.stadtteil,
    )
    report.rent_estimate = rent_estimate

    # Use mid-point rent for cashflow unless user provided override
    rent_for_cashflow = rent_kalt_override or listing.ist_miete_kalt or rent_estimate.miete_kalt_mid or None

    # ── Step 3: Cashflow ─────────────────────────────────────────────────────
    logger.info(f"[{job_id}] Running cashflow engine...")
    try:
        cashflow, red_flags = run_cashflow(
            listing=listing,
            params=financing_params,
            rent_kalt_monthly=rent_for_cashflow,
            renovation_plan_eur=renovation_plan_eur,
            marginal_tax_rate=marginal_tax_rate,
        )
        cashflow.miete_kalt_source = rent_estimate.source.name if rent_estimate.source else "Nutzereingabe"
        report.cashflow = cashflow
        report.red_flags = red_flags
        report.cashflow_complete = True
    except Exception as e:
        report.errors.append(f"Cashflow calculation failed: {e}")
        logger.error(f"[{job_id}] Cashflow error: {e}")
        return report

    # ── Step 4: Deal score ───────────────────────────────────────────────────
    report.deal_score = score_deal(cashflow, red_flags, rent_estimate)

    # ── Collect sources ───────────────────────────────────────────────────────
    if rent_estimate.source:
        report.sources.append(rent_estimate.source)

    report.report_complete = True
    logger.info(f"[{job_id}] Analysis complete. Score: {report.deal_score.score if report.deal_score else 'N/A'}")
    return report
