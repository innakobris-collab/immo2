"""
German tax calculations for buy-to-rent investment properties.
All calculations are deterministic — no LLM involved.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import date
from ..models.financials import AcquisitionCosts, AfaResult

_DATA_DIR = Path(__file__).parent.parent / "data"

with open(_DATA_DIR / "grunderwerbsteuer.json", encoding="utf-8") as f:
    _GREST_DATA = json.load(f)

with open(_DATA_DIR / "afa_rules.json", encoding="utf-8") as f:
    _AFA_DATA = json.load(f)


# ─── Grunderwerbsteuer ────────────────────────────────────────────────────────

def get_grunderwerbsteuer_rate(bundesland: str) -> float:
    """Return Grunderwerbsteuer rate (0.035–0.065) for the given Bundesland.
    Raises ValueError if Bundesland is unknown.
    """
    aliases = _GREST_DATA.get("_aliases", {})
    key = aliases.get(bundesland, bundesland)
    rate = _GREST_DATA.get(key)
    if rate is None:
        raise ValueError(
            f"Unknown Bundesland: '{bundesland}'. "
            f"Valid: {[k for k in _GREST_DATA if not k.startswith('_')]}"
        )
    return rate


def list_bundeslaender() -> list[str]:
    return [k for k in _GREST_DATA if not k.startswith("_")]


# ─── Acquisition costs ────────────────────────────────────────────────────────

def calculate_acquisition_costs(
    kaufpreis: float,
    bundesland: str,
    makler_pct: float = 0.0357,     # 3.57% buyer side for investment properties
    notar_grundbuch_pct: float = 0.017,
) -> AcquisitionCosts:
    grest_pct = get_grunderwerbsteuer_rate(bundesland)
    grest = kaufpreis * grest_pct
    notar = kaufpreis * notar_grundbuch_pct
    makler = kaufpreis * makler_pct
    nebenkosten = grest + notar + makler
    return AcquisitionCosts(
        kaufpreis=kaufpreis,
        grunderwerbsteuer_pct=grest_pct,
        grunderwerbsteuer=round(grest, 2),
        notar_grundbuch_pct=notar_grundbuch_pct,
        notar_grundbuch=round(notar, 2),
        makler_pct=makler_pct,
        makler=round(makler, 2),
        kaufnebenkosten_total=round(nebenkosten, 2),
        gesamtinvestition=round(kaufpreis + nebenkosten, 2),
    )


# ─── AfA (Depreciation) ───────────────────────────────────────────────────────

def determine_afa_type(
    baujahr: int | None,
    bauantrag_date: date | None = None,
    purchase_contract_date: date | None = None,
    is_neubau: bool = False,
) -> str:
    """Determine which AfA type applies.
    Returns one of: 'linear_2pct', 'linear_2_5pct', 'linear_3pct', 'sonder_afa', 'degressiv'
    """
    # Degressive AfA: purchase contract Oct 2023 – Sept 2029
    if purchase_contract_date:
        degressiv_start = date(2023, 10, 1)
        degressiv_end = date(2029, 9, 30)
        if degressiv_start <= purchase_contract_date <= degressiv_end and is_neubau:
            return "degressiv"

    # Sonder-AfA: Bauantrag Jan 2023 – Sept 2030 (extended)
    if bauantrag_date:
        sonder_start = date(2023, 1, 1)
        sonder_end = date(2030, 9, 30)
        if sonder_start <= bauantrag_date <= sonder_end and is_neubau:
            return "sonder_afa"

    # New construction (completed 2023+)
    if baujahr and baujahr >= 2023:
        return "linear_3pct"

    # Old building (pre-1925)
    if baujahr and baujahr < 1925:
        return "linear_2_5pct"

    # Standard (default)
    return "linear_2pct"


def calculate_afa(
    kaufpreis: float,
    baujahr: int | None,
    gebaeude_anteil_pct: float = 75.0,
    afa_type: str | None = None,
    bauantrag_date: date | None = None,
    purchase_contract_date: date | None = None,
    is_neubau: bool = False,
    wohnflaeche_m2: float | None = None,
) -> AfaResult:
    """Calculate annual AfA for year 1.
    gebaeude_anteil_pct: percentage of Kaufpreis attributable to the building
                         (remainder = Grundanteil, which cannot be depreciated).
    """
    if afa_type is None:
        afa_type = determine_afa_type(baujahr, bauantrag_date, purchase_contract_date, is_neubau)

    gebaeude_wert = kaufpreis * (gebaeude_anteil_pct / 100)

    if afa_type == "linear_2pct":
        rate = 0.02
        afa_annual = gebaeude_wert * rate
        sonder = 0.0
        note = "Standard 2% linear AfA (Baujahr 1925–2022)"

    elif afa_type == "linear_2_5pct":
        rate = 0.025
        afa_annual = gebaeude_wert * rate
        sonder = 0.0
        note = "2.5% linear AfA for pre-1925 buildings"

    elif afa_type == "linear_3pct":
        rate = 0.03
        afa_annual = gebaeude_wert * rate
        sonder = 0.0
        note = "3% linear AfA — Neubau completed on/after 01.01.2023"

    elif afa_type == "sonder_afa":
        rate = 0.03
        afa_annual = gebaeude_wert * rate
        # Sonder-AfA limited to €4,000/m² of Gebäudewert for calculation base
        afa_base_limit = (wohnflaeche_m2 * 4000) if wohnflaeche_m2 else gebaeude_wert
        sonder_base = min(gebaeude_wert, afa_base_limit)
        sonder = sonder_base * 0.05
        note = (
            f"3% linear + 5% Sonder-AfA §7b EStG (Bauantrag 2023–2030). "
            f"AfA base cap: €{afa_base_limit:,.0f} (€4,000/m²)."
        )

    elif afa_type == "degressiv":
        rate = 0.05
        afa_annual = gebaeude_wert * rate  # year 1 = 5% of full value
        sonder = 0.0
        note = (
            "5% degressive AfA §7(5a) EStG on residual book value. "
            "Year-1 calculation shown. Book value declines each year."
        )
    else:
        raise ValueError(f"Unknown AfA type: {afa_type}")

    total_year1 = afa_annual + sonder

    return AfaResult(
        afa_typ=afa_type,
        gebaeude_anteil_pct=gebaeude_anteil_pct,
        gebaeude_wert=round(gebaeude_wert, 2),
        afa_annual=round(afa_annual, 2),
        afa_rate_pct=rate * 100,
        sonder_afa_annual=round(sonder, 2),
        afa_total_year1=round(total_year1, 2),
        notes=note,
    )


# ─── Income tax estimate ──────────────────────────────────────────────────────

def estimate_income_tax_rate(annual_income_eur: float) -> float:
    """Approximate German marginal income tax rate for typical investor incomes.
    Simplified — use as indicative only. Ignores Soli, Kirchensteuer, filing status.
    Source: § 32a EStG (2024 tax schedule).
    """
    if annual_income_eur <= 11784:
        return 0.0
    elif annual_income_eur <= 17005:
        # Progressive zone 1: ~14%–24%
        return 0.14 + (annual_income_eur - 11784) * (0.24 - 0.14) / (17005 - 11784)
    elif annual_income_eur <= 66760:
        # Progressive zone 2: ~24%–42%
        return 0.24 + (annual_income_eur - 17005) * (0.42 - 0.24) / (66760 - 17005)
    elif annual_income_eur <= 277825:
        return 0.42
    else:
        return 0.45


# ─── Spekulationssteuer ───────────────────────────────────────────────────────

def calculate_spekulationssteuer(
    kaufpreis: float,
    sale_price: float,
    purchase_date: date,
    sale_date: date,
    marginal_tax_rate: float = 0.42,
    accumulated_afa: float = 0.0,
) -> dict:
    """Calculate Spekulationssteuer on property sale.
    Returns dict with: applies, tax_amount, net_gain, holding_years.

    The taxable gain is: sale_price - (adjusted_book_value)
    adjusted_book_value = kaufpreis - accumulated_afa (afa reduces book value)
    """
    holding_years = (sale_date - purchase_date).days / 365.25
    applies = holding_years < 10.0

    adjusted_book_value = kaufpreis - accumulated_afa
    gross_gain = sale_price - adjusted_book_value

    if not applies or gross_gain <= 0:
        tax = 0.0
    else:
        # Annual gain allowance: €1,000 (Wachstumschancengesetz 2024)
        taxable_gain = max(0.0, gross_gain - 1000.0)
        tax = taxable_gain * marginal_tax_rate

    return {
        "applies": applies,
        "holding_years": round(holding_years, 1),
        "gross_gain": round(gross_gain, 2),
        "adjusted_book_value": round(adjusted_book_value, 2),
        "spekulationssteuer": round(tax, 2),
        "net_gain": round(gross_gain - tax, 2),
        "note": (
            "Tax-free: holding period ≥ 10 years (Spekulationssteuer §23 EStG). "
            "Start date = notarized Kaufvertragsdatum."
        ),
    }


# ─── Verlustverrechnung estimate ─────────────────────────────────────────────

def estimate_tax_refund_from_rental_loss(
    verlust_vv: float,
    marginal_tax_rate: float,
    year: int = 2025,
) -> float:
    """Estimate annual tax refund from rental income loss (negative Einkünfte aus V&V).
    The loss offsets employment income in the same year → reduces tax bill.
    2024–2027: 70% carryforward; returns to 60% in 2028.
    For same-year offset (no carryforward needed for typical small investors): 100% usable.
    """
    if verlust_vv >= 0:
        return 0.0  # no loss, no refund
    loss = abs(verlust_vv)
    # For individual investors with employment income, same-year full offset applies
    # The 70%/60% rule applies to carryforward, not same-year offset
    refund = loss * marginal_tax_rate
    return round(refund, 2)
