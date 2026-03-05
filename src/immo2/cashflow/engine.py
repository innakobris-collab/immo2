"""
Main cashflow engine — orchestrates all calculation modules.
Input: ExtractedListing + FinancingParams
Output: CashflowModel
"""
from __future__ import annotations
from ..models.listing import ExtractedListing
from ..models.financials import (
    FinancingParams, CashflowModel, CashflowRow
)
from ..models.report import RedFlag
from .german_tax import (
    calculate_acquisition_costs, calculate_afa, estimate_income_tax_rate
)
from .weg_costs import split_hausgeld, estimate_hausgeld_from_m2
from .financing import (
    calculate_darlehen, monthly_annuity, amortization_schedule,
    calculate_dscr, calculate_yields
)
from .irr import build_exit_scenario, calculate_15pct_threshold
from .red_flags import run_all_checks
from ..config import settings


def run_cashflow(
    listing: ExtractedListing,
    params: FinancingParams | None = None,
    rent_kalt_monthly: float | None = None,
    renovation_plan_eur: float = 0.0,
    marginal_tax_rate: float = 0.42,
    price_growth_pct: float = 2.5,
) -> tuple[CashflowModel, list[RedFlag]]:
    """Main entry point. Returns (CashflowModel, list[RedFlag]).

    Raises ValueError if required fields are missing.
    """
    # ── Validate required fields ─────────────────────────────────────────────
    missing = listing.requires_user_input
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    kaufpreis = listing.kaufpreis
    wohnflaeche = listing.wohnflaeche_m2
    bundesland = listing.bundesland

    if params is None:
        params = FinancingParams(
            eigenkapital_pct=settings.default_eigenkapital_pct,
            finanzierungszins=settings.default_finanzierungszins,
            tilgung_pct=settings.default_tilgung_pct,
        )

    # ── Acquisition costs ────────────────────────────────────────────────────
    acquisition = calculate_acquisition_costs(
        kaufpreis=kaufpreis,
        bundesland=bundesland,
        makler_pct=settings.default_makler_pct / 100,
        notar_grundbuch_pct=settings.default_notar_grundbuch_pct / 100,
    )

    # ── AfA ─────────────────────────────────────────────────────────────────
    afa_result = calculate_afa(
        kaufpreis=kaufpreis,
        baujahr=listing.baujahr,
        gebaeude_anteil_pct=settings.default_grundanteil_pct
            and (100 - settings.default_grundanteil_pct) or 75.0,
        wohnflaeche_m2=wohnflaeche,
    )

    # ── Hausgeld ─────────────────────────────────────────────────────────────
    if listing.hausgeld_total:
        hg = split_hausgeld(listing.hausgeld_total)
    else:
        est = estimate_hausgeld_from_m2(wohnflaeche, listing.baujahr)
        hg = split_hausgeld(est["hausgeld_mid"])

    hausgeld_deductible = hg["hausgeld_deductible"]
    hausgeld_ruecklage = hg["hausgeld_ruecklage"]

    # ── Rent estimate ────────────────────────────────────────────────────────
    # If rent_kalt_monthly not provided, use existing rent from listing or placeholder
    if rent_kalt_monthly is None:
        rent_kalt_monthly = listing.ist_miete_kalt or (wohnflaeche * 12.0)

    # ── Financing ────────────────────────────────────────────────────────────
    darlehen = calculate_darlehen(kaufpreis, params)
    eigenkapital = kaufpreis * (params.eigenkapital_pct / 100)
    annuity_m, zinsen_m, tilgung_m = monthly_annuity(darlehen, params)
    amort = amortization_schedule(darlehen, params, years=10)

    # ── Key metrics ──────────────────────────────────────────────────────────
    grundsteuer_monthly = (listing.grundsteuer_annual or 0.0) / 12
    verwaltung_monthly = settings.default_verwaltung_monthly

    dscr = calculate_dscr(
        miete_kalt_annual=rent_kalt_monthly * 12,
        zinsen_annual=zinsen_m * 12,
        tilgung_annual=tilgung_m * 12,
    )

    yields = calculate_yields(
        kaufpreis=kaufpreis,
        miete_kalt_annual=rent_kalt_monthly * 12,
        hausgeld_deductible_annual=hausgeld_deductible * 12,
        hausgeld_ruecklage_annual=hausgeld_ruecklage * 12,
        grundsteuer_annual=listing.grundsteuer_annual or 0.0,
        verwaltung_annual=verwaltung_monthly * 12,
        eigenkapital=eigenkapital,
        zinsen_annual=zinsen_m * 12,
        afa_annual=afa_result.afa_total_year1,
        marginal_tax_rate=marginal_tax_rate,
    )

    # ── 10-year cashflow rows ─────────────────────────────────────────────────
    rows: list[CashflowRow] = []
    accumulated_afa = 0.0
    annual_cashflows_nst: list[float] = []
    rent_growth = 0.02  # 2% annual rent growth assumption

    for i, sched in enumerate(amort):
        yr = i + 1
        rent_yr = rent_kalt_monthly * 12 * ((1 + rent_growth) ** (yr - 1))
        zinsen_yr = sched["zinsen_annual"]
        tilgung_yr = sched["tilgung_annual"]

        # AfA for this year (simplified: same rate, declining for degressiv)
        if afa_result.afa_typ == "degressiv" and accumulated_afa > 0:
            remaining_book = afa_result.gebaeude_wert - accumulated_afa
            afa_yr = remaining_book * 0.05
        elif afa_result.afa_typ == "sonder_afa" and yr <= 4:
            afa_yr = afa_result.afa_total_year1
        elif afa_result.afa_typ == "sonder_afa":
            afa_yr = afa_result.afa_annual  # base rate after Sonder-AfA period
        else:
            afa_yr = afa_result.afa_annual
        accumulated_afa += afa_yr

        deductible_yr = hausgeld_deductible * 12
        ruecklage_yr = hausgeld_ruecklage * 12
        grundsteuer_yr = listing.grundsteuer_annual or 0.0

        cashflow_vst = rent_yr - zinsen_yr - deductible_yr - ruecklage_yr - grundsteuer_yr - verwaltung_monthly * 12
        steuerliches_ergebnis = rent_yr - deductible_yr - grundsteuer_yr - verwaltung_monthly * 12 - zinsen_yr - afa_yr
        steuererstattung = abs(min(steuerliches_ergebnis, 0)) * marginal_tax_rate if steuerliches_ergebnis < 0 else 0.0
        steuerbelastung = steuerliches_ergebnis * marginal_tax_rate if steuerliches_ergebnis > 0 else 0.0
        cashflow_nst = cashflow_vst + steuererstattung - steuerbelastung

        annual_cashflows_nst.append(cashflow_nst)
        rows.append(CashflowRow(
            year=yr,
            miete_kalt=round(rent_yr, 2),
            zinsen=round(zinsen_yr, 2),
            tilgung=round(tilgung_yr, 2),
            hausgeld_deductible=round(deductible_yr, 2),
            hausgeld_ruecklage=round(ruecklage_yr, 2),
            grundsteuer=round(grundsteuer_yr, 2),
            verwaltung=round(verwaltung_monthly * 12, 2),
            afa=round(afa_yr, 2),
            cashflow_vor_steuer=round(cashflow_vst, 2),
            steuerlicher_verlust_vv=round(steuerliches_ergebnis, 2),
            steuererstattung_estimate=round(steuererstattung, 2),
            cashflow_nach_steuer=round(cashflow_nst, 2),
            restschuld=sched["restschuld"],
        ))

    # ── Exit scenarios ────────────────────────────────────────────────────────
    restschuld_yr10 = amort[9]["restschuld"] if len(amort) >= 10 else darlehen
    restschuld_yr11 = amort[9]["restschuld"] if len(amort) >= 10 else darlehen  # same for yr 11

    exit_yr10 = build_exit_scenario(
        kaufpreis=kaufpreis,
        gesamtinvestition=acquisition.gesamtinvestition,
        eigenkapital=eigenkapital,
        annual_cashflows_nst=annual_cashflows_nst,
        restschuld=restschuld_yr10,
        exit_year=10,
        assumed_price_growth_pct=price_growth_pct,
        marginal_tax_rate=marginal_tax_rate,
        accumulated_afa=accumulated_afa,
    )

    # Year 11: tax-free (Spekulationssteuer does not apply after 10yr)
    exit_yr11 = build_exit_scenario(
        kaufpreis=kaufpreis,
        gesamtinvestition=acquisition.gesamtinvestition,
        eigenkapital=eigenkapital,
        annual_cashflows_nst=annual_cashflows_nst,
        restschuld=restschuld_yr11,
        exit_year=11,
        assumed_price_growth_pct=price_growth_pct,
        marginal_tax_rate=0.0,  # tax-free after 10yr
        accumulated_afa=accumulated_afa,
    )

    # ── 15% Erhaltungsaufwand ─────────────────────────────────────────────────
    threshold = calculate_15pct_threshold(kaufpreis, afa_result.gebaeude_anteil_pct)

    # ── Assemble model ────────────────────────────────────────────────────────
    model = CashflowModel(
        acquisition=acquisition,
        afa=afa_result,
        financing=params,
        miete_kalt_estimate=rent_kalt_monthly,
        hausgeld_total=listing.hausgeld_total or 0.0,
        hausgeld_deductible=hausgeld_deductible,
        hausgeld_ruecklage=hausgeld_ruecklage,
        grundsteuer_monthly=grundsteuer_monthly,
        verwaltung_monthly=verwaltung_monthly,
        darlehen=darlehen,
        zinsen_monthly_year1=zinsen_m,
        tilgung_monthly_year1=tilgung_m,
        annuitaet_monthly=annuity_m,
        bruttomietrendite_pct=yields["bruttomietrendite_pct"],
        nettomietrendite_pct=yields["nettomietrendite_pct"],
        cashflow_vor_steuer_monthly=yields["cashflow_vor_steuer_monthly"],
        cashflow_nach_steuer_monthly=yields["cashflow_nach_steuer_monthly"],
        eigenkapitalrendite_pct=yields["eigenkapitalrendite_pct"],
        dscr=dscr,
        rows=rows,
        exit_yr10_taxed=exit_yr10,
        exit_yr11_free=exit_yr11,
        erhaltungsaufwand_threshold=threshold,
        renovation_plan_amount=renovation_plan_eur,
        erhaltungsaufwand_flag=renovation_plan_eur >= threshold,
        assumptions={
            "Grundanteil": f"{100 - afa_result.gebaeude_anteil_pct:.0f}% des Kaufpreises",
            "Gebäudeanteil": f"{afa_result.gebaeude_anteil_pct:.0f}% des Kaufpreises",
            "AfA-Typ": afa_result.afa_typ,
            "Hausgeld deductible": f"{hg['deductible_pct_used']*100:.0f}% angenommen",
            "Eigenkapital": f"{params.eigenkapital_pct:.0f}% des Kaufpreises",
            "Zinssatz": f"{params.finanzierungszins:.2f}%",
            "Tilgung": f"{params.tilgung_pct:.2f}%",
            "Mietrendite Grundlage": "Nutzereingabe oder Mietspiegel",
            "Miete Wachstum": "2%/Jahr (Annahme)",
            "Grenzsteuersatz": f"{marginal_tax_rate*100:.0f}%",
            "Preissteigerung für Exit": f"{price_growth_pct:.1f}%/Jahr (Annahme)",
        },
    )

    # ── Red flags ─────────────────────────────────────────────────────────────
    flags = run_all_checks(
        energieklasse=listing.energieklasse,
        baujahr=listing.baujahr,
        heizung_baujahr=listing.heizung_baujahr,
        stadt=listing.stadt,
        plz=listing.plz,
        renovation_plan_eur=renovation_plan_eur,
        threshold_15pct=threshold,
        dscr=dscr,
    )

    return model, flags
