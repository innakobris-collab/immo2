"""
Rule-based Deal Score (0-100).
Transparent, explainable. No LLM — fully deterministic.
"""
from __future__ import annotations
from ..models.financials import CashflowModel, DealScore
from ..models.report import RedFlag, RentEstimate


def score_deal(
    cashflow: CashflowModel,
    red_flags: list[RedFlag],
    rent_estimate: RentEstimate | None,
) -> DealScore:
    """Calculate deal score 0-100.
    Components:
    - Yield score (30 pts): Bruttomietrendite vs. benchmark
    - Cashflow score (25 pts): DSCR + monthly cashflow nach Steuer
    - Risk penalty (30 pts): deducted for red flags
    - IRR score (15 pts): 10yr tax-free IRR
    """
    score = 0
    breakdown: dict[str, int] = {}

    # ── Yield (30 pts) ───────────────────────────────────────────────────────
    brutto = cashflow.bruttomietrendite_pct
    if brutto >= 5.0:
        yield_pts = 30
    elif brutto >= 4.5:
        yield_pts = 25
    elif brutto >= 4.0:
        yield_pts = 20
    elif brutto >= 3.5:
        yield_pts = 15
    elif brutto >= 3.0:
        yield_pts = 10
    else:
        yield_pts = 5
    breakdown["Mietrendite"] = yield_pts
    score += yield_pts

    # ── Cashflow / DSCR (25 pts) ─────────────────────────────────────────────
    dscr = cashflow.dscr
    cf_monthly = cashflow.cashflow_nach_steuer_monthly
    if dscr >= 1.30 and cf_monthly >= 200:
        cf_pts = 25
    elif dscr >= 1.20:
        cf_pts = 20
    elif dscr >= 1.10:
        cf_pts = 15
    elif dscr >= 1.0:
        cf_pts = 8
    else:
        cf_pts = 0
    breakdown["Cashflow/DSCR"] = cf_pts
    score += cf_pts

    # ── IRR (15 pts) ─────────────────────────────────────────────────────────
    irr = cashflow.exit_yr11_free.irr_pct if cashflow.exit_yr11_free else 0.0
    if irr >= 8.0:
        irr_pts = 15
    elif irr >= 6.0:
        irr_pts = 12
    elif irr >= 4.0:
        irr_pts = 8
    elif irr >= 2.0:
        irr_pts = 4
    else:
        irr_pts = 0
    breakdown["IRR 10yr"] = irr_pts
    score += irr_pts

    # ── Risk deductions (30 pts available) ───────────────────────────────────
    risk_deduction = 0
    for flag in red_flags:
        if flag.severity == "critical":
            risk_deduction += 12
        elif flag.severity == "warning":
            risk_deduction += 5
    risk_deduction = min(risk_deduction, 30)
    breakdown["Risiko-Abzug"] = -risk_deduction
    score -= risk_deduction

    score = max(0, min(100, score))

    # ── Grade ────────────────────────────────────────────────────────────────
    if score >= 75:
        grade = "strong_buy"
        headline = f"Starkes Investment: {brutto:.1f}% Rendite, DSCR {dscr:.2f}, keine kritischen Risiken."
    elif score >= 60:
        grade = "buy"
        headline = f"Gutes Investment: {brutto:.1f}% Rendite, DSCR {dscr:.2f}."
    elif score >= 45:
        grade = "watch"
        headline = f"Mittelmäßig: {brutto:.1f}% Rendite. Risiken vorhanden — sorgfältig prüfen."
    elif score >= 30:
        grade = "avoid"
        headline = f"Kritisch: {brutto:.1f}% Rendite und/oder erhebliche Risiken."
    else:
        grade = "critical_risk"
        headline = "Nicht empfehlenswert: Rendite zu niedrig oder kritische Risiken nicht bewältigbar."

    # ── Pros / Cons ──────────────────────────────────────────────────────────
    pros: list[str] = []
    cons: list[str] = []

    if brutto >= 4.0:
        pros.append(f"Bruttomietrendite {brutto:.1f}% — über Marktdurchschnitt (~3.5%)")
    if dscr >= 1.20:
        pros.append(f"DSCR {dscr:.2f} — Miete deckt Schuldendienst komfortabel")
    if irr >= 6.0 and cashflow.exit_yr11_free:
        pros.append(f"IRR {irr:.1f}% nach 10 Jahren (steuerfrei)")
    if cashflow.cashflow_nach_steuer_monthly > 0:
        pros.append(f"Positiver Cashflow nach Steuer: +€{cashflow.cashflow_nach_steuer_monthly:.0f}/Monat")
    if cashflow.afa.afa_total_year1 > 0:
        pros.append(f"AfA-Steuereffekt: €{cashflow.afa.afa_total_year1:.0f}/Jahr steuerlich absetzbar")

    critical_flags = [f for f in red_flags if f.severity == "critical"]
    warning_flags = [f for f in red_flags if f.severity == "warning"]
    for flag in critical_flags[:2]:
        cons.append(f"KRITISCH: {flag.title}")
    for flag in warning_flags[:1]:
        cons.append(f"Warnung: {flag.title}")
    if brutto < 3.5:
        cons.append(f"Rendite {brutto:.1f}% unter Marktdurchschnitt")
    if dscr < 1.0:
        cons.append("Cashflow-negativ: Zuzahlung aus Eigenmitteln nötig")

    return DealScore(
        score=score,
        grade=grade,
        headline=headline,
        pros=pros[:3],
        cons=cons[:3],
        score_breakdown=breakdown,
    )
