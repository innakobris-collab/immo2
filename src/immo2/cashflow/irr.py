"""
IRR and 10-year exit scenario calculations.
Includes Spekulationssteuer cliff at year 10.
"""
from __future__ import annotations
import math
from ..models.financials import ExitScenario


def calculate_irr(cashflows: list[float], max_iterations: int = 1000, tol: float = 1e-6) -> float:
    """Calculate Internal Rate of Return using Newton-Raphson method.
    cashflows[0] = initial investment (negative), subsequent = annual net cashflows.
    Returns IRR as a percentage (e.g. 6.5 for 6.5%).
    Returns NaN if no solution found.
    """
    if len(cashflows) < 2:
        return float("nan")

    rate = 0.10  # initial guess

    for _ in range(max_iterations):
        npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cashflows))
        d_npv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cashflows))
        if abs(d_npv) < 1e-12:
            break
        new_rate = rate - npv / d_npv
        if abs(new_rate - rate) < tol:
            return round(new_rate * 100, 2)
        rate = new_rate

    return float("nan")


def build_exit_scenario(
    kaufpreis: float,
    gesamtinvestition: float,     # kaufpreis + Kaufnebenkosten
    eigenkapital: float,
    annual_cashflows_nst: list[float],  # net after-tax cashflows years 1..N
    restschuld: float,
    exit_year: int,
    assumed_price_growth_pct: float = 2.5,  # annual % price appreciation
    marginal_tax_rate: float = 0.42,
    accumulated_afa: float = 0.0,
) -> ExitScenario:
    """Build exit scenario at a given year.
    Sale price = kaufpreis grown at assumed_price_growth_pct/year.
    """
    sale_price = kaufpreis * ((1 + assumed_price_growth_pct / 100) ** exit_year)
    sale_price = round(sale_price, 2)

    applies_spekst = exit_year < 10
    adjusted_book_value = kaufpreis - accumulated_afa
    gross_gain = sale_price - adjusted_book_value

    if applies_spekst and gross_gain > 0:
        taxable_gain = max(0.0, gross_gain - 1000.0)  # €1K annual allowance
        spekst = taxable_gain * marginal_tax_rate
    else:
        spekst = 0.0

    net_gain = gross_gain - spekst
    net_sale_proceeds = sale_price - restschuld - spekst

    # IRR cashflows: initial outflow (equity) + annual cashflows + terminal value
    cf = [-eigenkapital] + list(annual_cashflows_nst[:exit_year]) + [net_sale_proceeds]
    irr_pct = calculate_irr(cf)

    return ExitScenario(
        exit_year=exit_year,
        sale_price_assumed=sale_price,
        restschuld=round(restschuld, 2),
        gewinn_brutto=round(gross_gain, 2),
        spekulationssteuer_applies=applies_spekst,
        spekulationssteuer=round(spekst, 2),
        gewinn_netto=round(net_gain, 2),
        irr_pct=irr_pct if not math.isnan(irr_pct) else 0.0,
    )


def calculate_15pct_threshold(
    kaufpreis: float,
    gebaeude_anteil_pct: float = 75.0,
) -> float:
    """Calculate the 15% Erhaltungsaufwand threshold.
    If renovation costs in first 3 years after purchase exceed this amount,
    ALL renovation costs must be capitalized (§6 Abs.1 Nr.1a EStG).
    """
    gebaeude_wert = kaufpreis * (gebaeude_anteil_pct / 100)
    return round(gebaeude_wert * 0.15, 2)
