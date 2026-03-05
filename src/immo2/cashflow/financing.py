"""
Mortgage and cashflow calculations.
All deterministic Python — no external API calls.
"""
from __future__ import annotations
import math
from ..models.financials import FinancingParams


def calculate_darlehen(kaufpreis: float, params: FinancingParams) -> float:
    """Calculate loan amount from equity percentage."""
    eigenkapital = kaufpreis * (params.eigenkapital_pct / 100)
    if params.finanzierungsbetrag_override:
        return params.finanzierungsbetrag_override
    return round(kaufpreis - eigenkapital, 2)


def monthly_annuity(darlehen: float, params: FinancingParams) -> tuple[float, float, float]:
    """Calculate monthly payment, interest portion (year 1), repayment portion (year 1).
    Returns: (annuity_monthly, zinsen_monthly_year1, tilgung_monthly_year1)
    """
    annual_rate = (params.finanzierungszins + params.tilgung_pct) / 100
    annuity_monthly = darlehen * annual_rate / 12
    zinsen_monthly = darlehen * (params.finanzierungszins / 100) / 12
    tilgung_monthly = annuity_monthly - zinsen_monthly
    return (
        round(annuity_monthly, 2),
        round(zinsen_monthly, 2),
        round(tilgung_monthly, 2),
    )


def amortization_schedule(
    darlehen: float,
    params: FinancingParams,
    years: int = 10,
) -> list[dict]:
    """Generate annual amortization rows.
    Returns list of dicts: {year, zinsen_annual, tilgung_annual, restschuld}
    """
    monthly_rate = params.finanzierungszins / 100 / 12
    annuity_m, _, _ = monthly_annuity(darlehen, params)
    restschuld = darlehen
    rows = []
    for year in range(1, years + 1):
        zinsen_year = 0.0
        tilgung_year = 0.0
        for _ in range(12):
            zinsen_m = restschuld * monthly_rate
            tilgung_m = annuity_m - zinsen_m
            restschuld -= tilgung_m
            zinsen_year += zinsen_m
            tilgung_year += tilgung_m
        rows.append({
            "year": year,
            "zinsen_annual": round(zinsen_year, 2),
            "tilgung_annual": round(tilgung_year, 2),
            "restschuld": round(max(restschuld, 0), 2),
        })
    return rows


def calculate_dscr(
    miete_kalt_annual: float,
    zinsen_annual: float,
    tilgung_annual: float,
) -> float:
    """Debt Service Coverage Ratio: annual rent / annual debt service.
    DSCR > 1.0 = rent covers full mortgage payment.
    Lender requirement typically ≥ 1.20.
    """
    debt_service = zinsen_annual + tilgung_annual
    if debt_service <= 0:
        return float("inf")
    return round(miete_kalt_annual / debt_service, 3)


def calculate_yields(
    kaufpreis: float,
    miete_kalt_annual: float,
    hausgeld_deductible_annual: float,
    hausgeld_ruecklage_annual: float,
    grundsteuer_annual: float,
    verwaltung_annual: float,
    eigenkapital: float,
    zinsen_annual: float,
    afa_annual: float,
    marginal_tax_rate: float = 0.42,
) -> dict:
    """Calculate key return metrics."""
    brutto = (miete_kalt_annual / kaufpreis) * 100

    # Netto: subtract non-financing property costs from gross rent
    netto_income = miete_kalt_annual - hausgeld_deductible_annual - hausgeld_ruecklage_annual - grundsteuer_annual - verwaltung_annual
    netto = (netto_income / kaufpreis) * 100

    # Cashflow vor Steuer: netto_income minus full mortgage payment
    cashflow_monthly_vst = (netto_income - zinsen_annual * 12 / 12) / 12  # rough
    cashflow_annual_vst = netto_income - zinsen_annual  # excl. tilgung (not a cost)

    # Steuerliches Ergebnis (V&V): rent minus all deductible costs including AfA
    ertrag_vv = miete_kalt_annual - hausgeld_deductible_annual - grundsteuer_annual - verwaltung_annual - zinsen_annual - afa_annual
    steuererstattung = abs(min(ertrag_vv, 0)) * marginal_tax_rate if ertrag_vv < 0 else 0.0
    steuerbelastung = ertrag_vv * marginal_tax_rate if ertrag_vv > 0 else 0.0

    cashflow_annual_nst = cashflow_annual_vst + steuererstattung - steuerbelastung

    # Eigenkapitalrendite (based on equity invested)
    ekg_rendite = (cashflow_annual_nst / eigenkapital * 100) if eigenkapital > 0 else 0.0

    return {
        "bruttomietrendite_pct": round(brutto, 2),
        "nettomietrendite_pct": round(netto, 2),
        "cashflow_vor_steuer_annual": round(cashflow_annual_vst, 2),
        "cashflow_nach_steuer_annual": round(cashflow_annual_nst, 2),
        "cashflow_vor_steuer_monthly": round(cashflow_annual_vst / 12, 2),
        "cashflow_nach_steuer_monthly": round(cashflow_annual_nst / 12, 2),
        "steuerliches_ergebnis_vv": round(ertrag_vv, 2),
        "steuererstattung_annual": round(steuererstattung, 2),
        "eigenkapitalrendite_pct": round(ekg_rendite, 2),
    }
