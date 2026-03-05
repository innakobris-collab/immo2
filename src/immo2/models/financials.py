from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal


class FinancingParams(BaseModel):
    eigenkapital_pct: float = Field(default=20.0, ge=0, le=100)  # % of Kaufpreis
    finanzierungszins: float = Field(default=3.5, ge=0, le=20)   # annual %
    tilgung_pct: float = Field(default=2.0, ge=0, le=20)          # annual %
    laufzeit_jahre: int = Field(default=30, ge=1, le=50)
    # Optional: override Kaufpreis for financing (if renovation financed too)
    finanzierungsbetrag_override: float | None = None


class AcquisitionCosts(BaseModel):
    kaufpreis: float
    grunderwerbsteuer_pct: float
    grunderwerbsteuer: float
    notar_grundbuch_pct: float
    notar_grundbuch: float
    makler_pct: float
    makler: float
    kaufnebenkosten_total: float
    gesamtinvestition: float             # kaufpreis + kaufnebenkosten


class AfaResult(BaseModel):
    afa_typ: Literal["linear_2pct", "linear_2_5pct", "linear_3pct", "sonder_afa", "degressiv"]
    gebaeude_anteil_pct: float
    gebaeude_wert: float
    afa_annual: float                    # year 1
    afa_rate_pct: float
    sonder_afa_annual: float = 0.0       # extra 5% for qualifying new builds
    afa_total_year1: float = 0.0         # afa_annual + sonder_afa_annual
    notes: str = ""


class CashflowRow(BaseModel):
    year: int
    miete_kalt: float
    zinsen: float
    tilgung: float
    hausgeld_deductible: float
    hausgeld_ruecklage: float
    grundsteuer: float
    verwaltung: float
    afa: float
    cashflow_vor_steuer: float
    steuerlicher_verlust_vv: float       # negative = tax loss → refund
    steuererstattung_estimate: float     # based on marginal rate
    cashflow_nach_steuer: float
    restschuld: float                    # remaining loan balance


class ExitScenario(BaseModel):
    exit_year: int
    sale_price_assumed: float
    restschuld: float
    gewinn_brutto: float
    spekulationssteuer_applies: bool
    spekulationssteuer: float
    gewinn_netto: float
    irr_pct: float


class CashflowModel(BaseModel):
    # ── Acquisition ────────────────────────────────────────────
    acquisition: AcquisitionCosts
    afa: AfaResult
    financing: FinancingParams

    # ── Monthly snapshot (year 1) ───────────────────────────────
    miete_kalt_estimate: float           # from Mietspiegel or user input
    miete_kalt_source: str = ""          # e.g. "Mietspiegel Berlin 2023"
    hausgeld_total: float = 0.0
    hausgeld_deductible: float = 0.0
    hausgeld_ruecklage: float = 0.0
    grundsteuer_monthly: float = 0.0
    verwaltung_monthly: float = 0.0

    # ── Mortgage ───────────────────────────────────────────────
    darlehen: float
    zinsen_monthly_year1: float
    tilgung_monthly_year1: float
    annuitaet_monthly: float

    # ── Returns ────────────────────────────────────────────────
    bruttomietrendite_pct: float
    nettomietrendite_pct: float
    cashflow_vor_steuer_monthly: float
    cashflow_nach_steuer_monthly: float  # year 1 estimate
    eigenkapitalrendite_pct: float
    dscr: float

    # ── 10yr projection ────────────────────────────────────────
    rows: list[CashflowRow] = Field(default_factory=list)
    exit_yr10_taxed: ExitScenario | None = None    # sell in year 10 (Spekulationssteuer)
    exit_yr11_free: ExitScenario | None = None     # sell in year 11+ (tax-free)

    # ── 15% Erhaltungsaufwand ───────────────────────────────────
    erhaltungsaufwand_threshold: float = 0.0       # absolute € amount
    renovation_plan_amount: float = 0.0
    erhaltungsaufwand_flag: bool = False            # True if threshold exceeded

    # ── Assumptions ────────────────────────────────────────────
    assumptions: dict[str, str] = Field(default_factory=dict)


class DealScore(BaseModel):
    score: int = Field(ge=0, le=100)
    grade: Literal["strong_buy", "buy", "watch", "avoid", "critical_risk"]
    headline: str                        # one sentence verdict
    pros: list[str] = Field(default_factory=list, max_length=3)
    cons: list[str] = Field(default_factory=list, max_length=3)
    score_breakdown: dict[str, int] = Field(default_factory=dict)
