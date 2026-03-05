from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from .listing import ExtractedListing, Source
from .financials import CashflowModel, DealScore


class RedFlag(BaseModel):
    severity: str   # "critical", "warning", "info"
    category: str   # "energy", "structure", "legal", "financial", "location"
    title: str
    description: str
    mitigation: str = ""
    source: str = ""


class RentEstimate(BaseModel):
    miete_kalt_low: float
    miete_kalt_mid: float
    miete_kalt_high: float
    per_m2_low: float
    per_m2_mid: float
    per_m2_high: float
    mietpreisbremse_applies: bool = False
    mietpreisbremse_cap: float | None = None
    neubau_exempt: bool = False          # post-2014 construction exempt
    source: Source | None = None
    city_in_corpus: bool = False         # False = estimate unavailable
    notes: str = ""


class AnalysisReport(BaseModel):
    # ── Identity ───────────────────────────────────────────────
    job_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: str = "0.1.0"

    # ── Inputs ─────────────────────────────────────────────────
    listing: ExtractedListing

    # ── Outputs ────────────────────────────────────────────────
    cashflow: CashflowModel | None = None
    rent_estimate: RentEstimate | None = None
    red_flags: list[RedFlag] = Field(default_factory=list)
    deal_score: DealScore | None = None

    # ── All sources used ───────────────────────────────────────
    sources: list[Source] = Field(default_factory=list)

    # ── Pipeline status ────────────────────────────────────────
    extraction_complete: bool = False
    cashflow_complete: bool = False
    report_complete: bool = False
    errors: list[str] = Field(default_factory=list)

    @property
    def critical_flags(self) -> list[RedFlag]:
        return [f for f in self.red_flags if f.severity == "critical"]

    @property
    def warning_flags(self) -> list[RedFlag]:
        return [f for f in self.red_flags if f.severity == "warning"]
