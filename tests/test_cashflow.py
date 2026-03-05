"""
Unit tests for the German cashflow engine.
All 20 tests must pass before shipping.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from immo2.cashflow.german_tax import (
    get_grunderwerbsteuer_rate,
    calculate_acquisition_costs,
    calculate_afa,
    determine_afa_type,
    calculate_spekulationssteuer,
)
from immo2.cashflow.weg_costs import split_hausgeld, estimate_hausgeld_from_m2
from immo2.cashflow.financing import calculate_dscr, monthly_annuity
from immo2.cashflow.irr import calculate_15pct_threshold, calculate_irr
from immo2.models.financials import FinancingParams
from datetime import date


# ── Grunderwerbsteuer ─────────────────────────────────────────────────────────

def test_grest_all_bundeslaender():
    """All 16 Bundesländer must return the correct 2025 rate."""
    rates = {
        "Bayern": 0.035,
        "Sachsen": 0.035,
        "Hamburg": 0.055,
        "Baden-Württemberg": 0.050,
        "Niedersachsen": 0.050,
        "Sachsen-Anhalt": 0.050,
        "Thüringen": 0.050,
        "Rheinland-Pfalz": 0.050,
        "Bremen": 0.050,
        "Berlin": 0.060,
        "Hessen": 0.060,
        "Mecklenburg-Vorpommern": 0.060,
        "Brandenburg": 0.065,
        "Nordrhein-Westfalen": 0.065,
        "Saarland": 0.065,
        "Schleswig-Holstein": 0.065,
    }
    for bundesland, expected_rate in rates.items():
        assert get_grunderwerbsteuer_rate(bundesland) == expected_rate, \
            f"{bundesland}: expected {expected_rate}, got {get_grunderwerbsteuer_rate(bundesland)}"


def test_grest_aliases():
    """Bundesland aliases (NRW, BY, BE, etc.) must resolve correctly."""
    assert get_grunderwerbsteuer_rate("NRW") == 0.065
    assert get_grunderwerbsteuer_rate("BY") == 0.035
    assert get_grunderwerbsteuer_rate("BE") == 0.060
    assert get_grunderwerbsteuer_rate("HH") == 0.055
    assert get_grunderwerbsteuer_rate("NI") == 0.050


def test_grest_unknown_raises():
    with pytest.raises(ValueError):
        get_grunderwerbsteuer_rate("Atlantis")


def test_acquisition_costs_berlin():
    """Berlin: 6% GrESt + 1.7% Notar + 3.57% Makler on €350K."""
    ac = calculate_acquisition_costs(350_000, "Berlin")
    assert ac.grunderwerbsteuer == pytest.approx(21_000, rel=0.001)
    assert ac.notar_grundbuch == pytest.approx(5_950, rel=0.01)
    assert ac.makler == pytest.approx(12_495, rel=0.01)
    assert ac.kaufnebenkosten_total == pytest.approx(39_445, rel=0.01)
    assert ac.gesamtinvestition == pytest.approx(389_445, rel=0.01)


def test_acquisition_costs_bavaria():
    """Bavaria: 3.5% GrESt — cheapest in Germany."""
    ac = calculate_acquisition_costs(400_000, "Bayern")
    assert ac.grunderwerbsteuer_pct == 0.035
    assert ac.grunderwerbsteuer == pytest.approx(14_000, rel=0.001)


# ── AfA ───────────────────────────────────────────────────────────────────────

def test_afa_standard_2pct():
    """Standard 2% AfA for pre-2023 buildings."""
    result = calculate_afa(kaufpreis=300_000, baujahr=1985, gebaeude_anteil_pct=75.0)
    assert result.afa_typ == "linear_2pct"
    assert result.gebaeude_wert == pytest.approx(225_000, rel=0.001)
    assert result.afa_annual == pytest.approx(4_500, rel=0.001)
    assert result.sonder_afa_annual == 0.0


def test_afa_altbau_2_5pct():
    """2.5% AfA for pre-1925 buildings."""
    result = calculate_afa(kaufpreis=500_000, baujahr=1905, gebaeude_anteil_pct=70.0)
    assert result.afa_typ == "linear_2_5pct"
    assert result.afa_rate_pct == 2.5
    assert result.afa_annual == pytest.approx(500_000 * 0.70 * 0.025, rel=0.001)


def test_afa_neubau_3pct():
    """3% AfA for new construction completed 2023+."""
    result = calculate_afa(kaufpreis=500_000, baujahr=2023, gebaeude_anteil_pct=80.0)
    assert result.afa_typ == "linear_3pct"
    assert result.afa_rate_pct == 3.0


def test_afa_sonder_afa():
    """Sonder-AfA: 3% base + 5% extra = 8% total in years 1-4."""
    result = calculate_afa(
        kaufpreis=400_000,
        baujahr=2024,
        gebaeude_anteil_pct=75.0,
        afa_type="sonder_afa",
        wohnflaeche_m2=80.0,
    )
    assert result.afa_typ == "sonder_afa"
    assert result.sonder_afa_annual > 0
    # Total year 1 = 3% + 5% of (min(gebäudewert, 80m²×4000))
    gebaeude_wert = 400_000 * 0.75  # 300,000
    afa_base_cap = 80 * 4000  # 320,000
    sonder_base = min(gebaeude_wert, afa_base_cap)
    expected_sonder = sonder_base * 0.05
    assert result.sonder_afa_annual == pytest.approx(expected_sonder, rel=0.001)


def test_afa_type_determination():
    """AfA type selection logic."""
    assert determine_afa_type(1985) == "linear_2pct"
    assert determine_afa_type(1910) == "linear_2_5pct"
    assert determine_afa_type(2023) == "linear_3pct"
    # Sonder-AfA: Bauantrag 2024
    assert determine_afa_type(2024, bauantrag_date=date(2024, 6, 1), is_neubau=True) == "sonder_afa"
    # Degressiv: purchase contract Oct 2024
    assert determine_afa_type(2024, purchase_contract_date=date(2024, 10, 15), is_neubau=True) == "degressiv"


# ── Hausgeld ──────────────────────────────────────────────────────────────────

def test_hausgeld_split_default():
    """65% of Hausgeld should be deductible by default."""
    result = split_hausgeld(300.0)
    assert result["hausgeld_deductible"] == pytest.approx(195.0, rel=0.001)
    assert result["hausgeld_ruecklage"] + result["hausgeld_other_nondeductible"] == \
           pytest.approx(105.0, rel=0.001)


def test_hausgeld_estimate():
    """Hausgeld estimate from m² should be reasonable."""
    result = estimate_hausgeld_from_m2(70.0, baujahr=1975)
    assert result["hausgeld_mid"] > 0
    assert result["is_estimate"] is True
    # Old building: should be higher than new
    old = estimate_hausgeld_from_m2(70.0, baujahr=1960)
    new = estimate_hausgeld_from_m2(70.0, baujahr=2020)
    assert old["hausgeld_mid"] > new["hausgeld_mid"]


# ── Financing ─────────────────────────────────────────────────────────────────

def test_dscr_calculation():
    """DSCR = annual rent / annual debt service."""
    dscr = calculate_dscr(12_000, 6_000, 2_000)
    assert dscr == pytest.approx(12_000 / 8_000, rel=0.001)


def test_monthly_annuity():
    """Annuity calculation: 3.5% Zins + 2% Tilgung on €280K."""
    params = FinancingParams(finanzierungszins=3.5, tilgung_pct=2.0)
    annuity, zinsen, tilgung = monthly_annuity(280_000, params)
    assert annuity == pytest.approx(280_000 * 0.055 / 12, rel=0.01)
    assert zinsen == pytest.approx(280_000 * 0.035 / 12, rel=0.01)
    assert zinsen + tilgung == pytest.approx(annuity, rel=0.001)


# ── IRR & 15% Rule ────────────────────────────────────────────────────────────

def test_15pct_threshold():
    """15% of Gebäudeanteil of Kaufpreis."""
    # Kaufpreis 350K, Gebäudeanteil 75%: threshold = 350K × 0.75 × 0.15 = 39,375
    threshold = calculate_15pct_threshold(350_000, 75.0)
    assert threshold == pytest.approx(39_375, rel=0.001)


def test_irr_simple():
    """IRR of simple cashflow [-100, +110] should be ~10%."""
    irr = calculate_irr([-100.0, 110.0])
    assert irr == pytest.approx(10.0, abs=0.1)


def test_irr_negative():
    """All-negative cashflow should return NaN."""
    import math
    irr = calculate_irr([-100.0, -50.0])
    assert math.isnan(irr) or irr < 0


# ── Spekulationssteuer ────────────────────────────────────────────────────────

def test_spekulationssteuer_applies_within_10yr():
    result = calculate_spekulationssteuer(
        kaufpreis=300_000,
        sale_price=380_000,
        purchase_date=date(2024, 3, 1),
        sale_date=date(2030, 3, 1),  # 6 years
        marginal_tax_rate=0.42,
    )
    assert result["applies"] is True
    assert result["gross_gain"] == pytest.approx(80_000, rel=0.001)
    assert result["spekulationssteuer"] > 0


def test_spekulationssteuer_free_after_10yr():
    result = calculate_spekulationssteuer(
        kaufpreis=300_000,
        sale_price=400_000,
        purchase_date=date(2014, 1, 1),
        sale_date=date(2024, 6, 1),  # > 10 years
        marginal_tax_rate=0.42,
    )
    assert result["applies"] is False
    assert result["spekulationssteuer"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
