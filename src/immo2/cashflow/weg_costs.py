"""
WEG (Wohnungseigentumsgemeinschaft) cost calculations.
Handles Hausgeld splitting: deductible vs non-deductible (Rücklage).
"""
from __future__ import annotations


DEFAULT_HAUSGELD_DEDUCTIBLE_PCT = 0.65  # ~65% deductible for typical WEG
DEFAULT_RUECKLAGE_PCT = 0.20            # ~20% goes to Instandhaltungsrücklage


def split_hausgeld(
    hausgeld_total: float,
    deductible_pct: float = DEFAULT_HAUSGELD_DEDUCTIBLE_PCT,
) -> dict[str, float]:
    """Split monthly Hausgeld into deductible and non-deductible portions.

    Deductible: Verwaltungskosten, Versicherungen, Hausmeister, Gartenpflege,
                laufende Instandhaltungsanteile (not the Rücklage itself).
    NOT deductible: Instandhaltungsrücklage (the reserve itself).

    In practice: ~60–70% of Hausgeld is deductible without the actual
    WEG-Jahresabrechnung. Use 65% as default. Override with actual data.

    Returns:
        hausgeld_deductible: monthly deductible amount
        hausgeld_ruecklage: estimated monthly Rücklage (not deductible)
        hausgeld_other_nondeductible: other non-deductible amounts
    """
    deductible = hausgeld_total * deductible_pct
    non_deductible = hausgeld_total * (1 - deductible_pct)
    # Approximate split of non-deductible: mostly Rücklage
    ruecklage = non_deductible * 0.80
    other = non_deductible * 0.20

    return {
        "hausgeld_total": round(hausgeld_total, 2),
        "hausgeld_deductible": round(deductible, 2),
        "hausgeld_ruecklage": round(ruecklage, 2),
        "hausgeld_other_nondeductible": round(other, 2),
        "deductible_pct_used": deductible_pct,
        "note": (
            "Estimated split — deductible ~65% (Verwaltung, Versicherung, Instandhaltungsanteile). "
            "Instandhaltungsrücklage is NOT deductible. "
            "Verify against actual WEG-Jahresabrechnung for precise calculation."
        ),
    }


def estimate_hausgeld_from_m2(
    wohnflaeche_m2: float,
    baujahr: int | None = None,
    has_aufzug: bool | None = None,
) -> dict[str, float]:
    """Estimate monthly Hausgeld from square meters when not stated in listing.
    Based on typical German WEG ranges.
    """
    # Base rate by age
    if baujahr is None:
        base_per_m2 = 3.50  # unknown age: use mid-range
    elif baujahr >= 2010:
        base_per_m2 = 2.50  # new build: lower
    elif baujahr >= 1990:
        base_per_m2 = 3.00
    elif baujahr >= 1970:
        base_per_m2 = 3.50
    else:
        base_per_m2 = 4.00  # older buildings: higher maintenance

    # Aufzug adds ~€0.40/m²/month
    if has_aufzug:
        base_per_m2 += 0.40

    hausgeld_low = wohnflaeche_m2 * (base_per_m2 - 0.75)
    hausgeld_mid = wohnflaeche_m2 * base_per_m2
    hausgeld_high = wohnflaeche_m2 * (base_per_m2 + 1.00)

    return {
        "hausgeld_low": round(hausgeld_low, 0),
        "hausgeld_mid": round(hausgeld_mid, 0),
        "hausgeld_high": round(hausgeld_high, 0),
        "per_m2_rate": base_per_m2,
        "is_estimate": True,
        "note": (
            f"Estimated {base_per_m2:.2f} €/m²/month. "
            "Verify against actual WEG documents."
        ),
    }
