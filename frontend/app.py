"""
Immo2 — Streamlit MVP UI
German buy-to-rent deal analysis in <90 seconds.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import nest_asyncio
nest_asyncio.apply()  # Allow asyncio.run() inside Streamlit event loop

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import streamlit as st


# Install Playwright browsers on first run (needed on Streamlit Cloud)
@st.cache_resource(show_spinner=False)
def _install_playwright_browsers():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
    )


_install_playwright_browsers()
from immo2.models.financials import FinancingParams
from immo2.models.report import AnalysisReport

st.set_page_config(
    page_title="immo2 — Deal Analysis",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main { max-width: 900px; margin: 0 auto; }
  .deal-score-green  { color: #2E7D32; font-size: 4rem; font-weight: 700; }
  .deal-score-yellow { color: #E65100; font-size: 4rem; font-weight: 700; }
  .deal-score-red    { color: #C62828; font-size: 4rem; font-weight: 700; }
  .flag-critical { background: #FFEBEE; border-left: 4px solid #C62828; padding: 10px 14px; margin: 6px 0; border-radius: 2px; }
  .flag-warning  { background: #FFF3E0; border-left: 4px solid #E65100; padding: 10px 14px; margin: 6px 0; border-radius: 2px; }
  .flag-info     { background: #E3F2FD; border-left: 4px solid #1565C0; padding: 10px 14px; margin: 6px 0; border-radius: 2px; }
  .metric-box { background: #FAFAFA; border: 1px solid #E0E0E0; border-radius: 4px; padding: 12px; text-align: center; }
  .conf-high   { color: #2E7D32; font-size: 0.75rem; }
  .conf-medium { color: #E65100; font-size: 0.75rem; }
  .conf-low    { color: #C62828; font-size: 0.75rem; }
</style>
""", unsafe_allow_html=True)


def confidence_indicator(conf: float) -> str:
    if conf >= 0.8:
        return '<span class="conf-high">▓▓▓ high</span>'
    elif conf >= 0.5:
        return '<span class="conf-medium">▓▓░ medium</span>'
    else:
        return '<span class="conf-low">▓░░ low</span>'


def score_color_class(score: int) -> str:
    if score >= 65:
        return "deal-score-green"
    elif score >= 45:
        return "deal-score-yellow"
    return "deal-score-red"


# ─────────────────────────────────────────────────────────────────────────────
# Page: Input
# ─────────────────────────────────────────────────────────────────────────────
def page_input():
    st.title("immo2")
    st.subheader("German Buy-to-Rent Deal Analysis")

    tab_pdf, tab_url, tab_manual = st.tabs(["📄 Upload PDF", "🔗 URL", "✏️ Manual"])

    with tab_pdf:
        uploaded = st.file_uploader("Upload Exposé PDF", type=["pdf"])
        if uploaded:
            st.session_state["input_type"] = "pdf"
            st.session_state["pdf_bytes"] = uploaded.read()
            st.success(f"PDF loaded: {uploaded.name} ({len(st.session_state['pdf_bytes'])//1024}KB)")

    with tab_url:
        url = st.text_input("Listing URL (IS24, Immowelt, or other)")
        if url:
            st.session_state["input_type"] = "url"
            st.session_state["input_url"] = url
            st.info("Single-page render — you must be able to view this URL in a browser.")

    with tab_manual:
        st.markdown("**Paste exposé text or enter key figures:**")
        manual_text = st.text_area("Exposé text (copy from browser or PDF)", height=200)
        if manual_text:
            st.session_state["input_type"] = "manual_text"
            st.session_state["manual_text"] = manual_text

    st.divider()

    # Financing parameters
    with st.expander("Financing assumptions (optional — defaults used if not changed)"):
        col1, col2, col3 = st.columns(3)
        with col1:
            eigenkapital_pct = st.number_input("Eigenkapital (%)", value=20.0, min_value=0.0, max_value=100.0, step=5.0)
        with col2:
            zinssatz = st.number_input("Zinssatz (%)", value=3.5, min_value=0.5, max_value=15.0, step=0.1)
        with col3:
            tilgung = st.number_input("Tilgung (%)", value=2.0, min_value=0.5, max_value=10.0, step=0.5)

        renovation = st.number_input("Geplante Renovierung erste 3 Jahre (€)", value=0, step=1000, min_value=0)
        tax_rate = st.number_input("Grenzsteuersatz (%)", value=42, min_value=14, max_value=45, step=1)

        st.session_state["financing"] = FinancingParams(
            eigenkapital_pct=eigenkapital_pct,
            finanzierungszins=zinssatz,
            tilgung_pct=tilgung,
        )
        st.session_state["renovation_eur"] = float(renovation)
        st.session_state["tax_rate"] = tax_rate / 100.0

    st.divider()
    ready = "input_type" in st.session_state
    if st.button("Analyze Deal", type="primary", disabled=not ready):
        st.session_state["page"] = "loading"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Page: Loading / Analysis
# ─────────────────────────────────────────────────────────────────────────────
def page_loading():
    st.title("Analyzing deal...")
    progress = st.progress(0)
    status = st.empty()

    async def run():
        from immo2.intake.pdf_extract import extract_from_pdf, extract_from_text
        from immo2.intake.playwright_fetch import fetch_url
        from immo2.agents.pipeline import run_analysis

        status.write("Step 1/4 — Extracting text from document...")
        progress.progress(10)

        input_type = st.session_state.get("input_type")
        if input_type == "pdf":
            raw = extract_from_pdf(st.session_state["pdf_bytes"])
        elif input_type == "url":
            raw = await fetch_url(st.session_state["input_url"])
            if not raw.raw_text.strip():
                st.error("Could not fetch URL — please upload the PDF or use manual entry.")
                st.session_state["page"] = "input"
                st.rerun()
                return None
        else:
            raw = extract_from_text(st.session_state.get("manual_text", ""))

        status.write("Step 2/4 — Extracting property data with AI...")
        progress.progress(35)

        report = await run_analysis(
            raw_listing=raw,
            financing_params=st.session_state.get("financing"),
            renovation_plan_eur=st.session_state.get("renovation_eur", 0.0),
            marginal_tax_rate=st.session_state.get("tax_rate", 0.42),
        )

        status.write("Step 3/4 — Calculating cashflow...")
        progress.progress(65)

        status.write("Step 4/4 — Generating report...")
        progress.progress(90)

        return report

    report = asyncio.run(run())
    progress.progress(100)

    if report:
        if not report.extraction_complete:
            st.error(f"Extraction failed: {'; '.join(report.errors)}")
            if st.button("← Try again"):
                st.session_state["page"] = "input"
                st.rerun()
            return

        # If missing required fields, show confirmation UI
        if not report.cashflow_complete:
            st.session_state["report"] = report
            st.session_state["page"] = "review"
        else:
            st.session_state["report"] = report
            st.session_state["page"] = "dashboard"

    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Page: Review extracted fields (confidence gate)
# ─────────────────────────────────────────────────────────────────────────────
def page_review():
    report: AnalysisReport = st.session_state.get("report")
    if not report:
        st.session_state["page"] = "input"
        st.rerun()
        return

    listing = report.listing
    st.title("Review Extracted Data")
    st.info("AI extracted the fields below. Review and correct before calculating.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Address & Property**")
        address = st.text_input("Address", value=listing.address or "")
        plz = st.text_input("PLZ", value=listing.plz or "")
        stadt = st.text_input("Stadt", value=listing.stadt or "")
        bundesland = st.selectbox("Bundesland *", options=[
            "", "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen",
            "Hamburg", "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen",
            "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen",
            "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen"
        ], index=0 if not listing.bundesland else None)
        wohnflaeche = st.number_input("Wohnfläche m² *", value=listing.wohnflaeche_m2 or 0.0, min_value=0.0)
        zimmer = st.number_input("Zimmer", value=listing.zimmer or 0.0, min_value=0.0, step=0.5)
        baujahr = st.number_input("Baujahr", value=listing.baujahr or 1900, min_value=1800, max_value=2030, step=1)

    with col2:
        st.markdown("**Financials**")
        kaufpreis = st.number_input("Kaufpreis € *", value=listing.kaufpreis or 0.0, min_value=0.0, step=1000.0)
        hausgeld = st.number_input("Hausgeld €/Monat", value=listing.hausgeld_total or 0.0, min_value=0.0, step=10.0)
        ist_miete = st.number_input("Aktuelle Kaltmiete €/Monat (0 = leer)", value=listing.ist_miete_kalt or 0.0, min_value=0.0, step=10.0)
        energieklasse = st.selectbox("Energieklasse", options=["", "A+", "A", "B", "C", "D", "E", "F", "G", "H"],
                                     index=0 if not listing.energieklasse else None)
        heizung_baujahr = st.number_input("Heizung Baujahr", value=listing.heizung_baujahr or 1990, min_value=1950, max_value=2026, step=1)

    if listing.extraction_confidence < 0.75:
        st.warning(f"Extraction confidence: {listing.extraction_confidence:.0%} — please verify all fields carefully.")

    required_ok = bundesland and wohnflaeche > 0 and kaufpreis > 0

    if st.button("Calculate", type="primary", disabled=not required_ok):
        # Update listing with user corrections
        listing.address = address or listing.address
        listing.plz = plz or listing.plz
        listing.stadt = stadt or listing.stadt
        listing.bundesland = bundesland or listing.bundesland
        listing.wohnflaeche_m2 = wohnflaeche
        listing.zimmer = zimmer or listing.zimmer
        listing.baujahr = int(baujahr) if baujahr else listing.baujahr
        listing.kaufpreis = kaufpreis
        listing.hausgeld_total = hausgeld if hausgeld > 0 else listing.hausgeld_total
        listing.ist_miete_kalt = ist_miete if ist_miete > 0 else listing.ist_miete_kalt
        listing.energieklasse = energieklasse or listing.energieklasse
        listing.heizung_baujahr = int(heizung_baujahr) if heizung_baujahr else listing.heizung_baujahr

        # Re-run cashflow with corrected data
        from immo2.cashflow.engine import run_cashflow
        from immo2.rag.mietspiegel_stubs import get_mietspiegel_estimate
        from immo2.cashflow.scoring import score_deal

        rent_est = get_mietspiegel_estimate(listing.stadt, listing.baujahr, listing.wohnflaeche_m2, listing.stadtteil, bundesland=listing.bundesland)
        report.rent_estimate = rent_est
        rent_for_cf = listing.ist_miete_kalt or rent_est.miete_kalt_mid or None

        cashflow, red_flags = run_cashflow(
            listing=listing,
            params=st.session_state.get("financing"),
            rent_kalt_monthly=rent_for_cf,
            renovation_plan_eur=st.session_state.get("renovation_eur", 0.0),
            marginal_tax_rate=st.session_state.get("tax_rate", 0.42),
        )
        report.cashflow = cashflow
        report.red_flags = red_flags
        report.cashflow_complete = True
        report.deal_score = score_deal(cashflow, red_flags, rent_est)
        st.session_state["report"] = report
        st.session_state["page"] = "dashboard"
        st.rerun()

    if st.button("← Back"):
        st.session_state["page"] = "input"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Page: Deal Dashboard
# ─────────────────────────────────────────────────────────────────────────────
def page_dashboard():
    report: AnalysisReport = st.session_state.get("report")
    if not report or not report.cashflow:
        st.session_state["page"] = "input"
        st.rerun()
        return

    cf = report.cashflow
    listing = report.listing
    score = report.deal_score
    rent = report.rent_estimate

    # Header
    col_title, col_actions = st.columns([3, 1])
    with col_title:
        st.title(listing.address or f"{listing.plz} {listing.stadt}")
    with col_actions:
        if st.button("← New Analysis"):
            for k in ["report", "input_type", "pdf_bytes", "input_url", "manual_text"]:
                st.session_state.pop(k, None)
            st.session_state["page"] = "input"
            st.rerun()

    # ── Deal Score ────────────────────────────────────────────────────────────
    st.divider()
    col_score, col_verdict = st.columns([1, 3])
    with col_score:
        cls = score_color_class(score.score)
        st.markdown(f'<div class="{cls}">{score.score}</div>', unsafe_allow_html=True)
        st.caption("Deal Score / 100")
    with col_verdict:
        st.markdown(f"**{score.headline}**")
        if score.pros:
            st.markdown("**Pros:** " + " · ".join(f"✓ {p}" for p in score.pros))
        if score.cons:
            st.markdown("**Cons:** " + " · ".join(f"✗ {c}" for c in score.cons))

    # ── Key metrics ───────────────────────────────────────────────────────────
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Brutto-Mietrendite", f"{cf.bruttomietrendite_pct:.2f}%",
                  delta=f"{cf.bruttomietrendite_pct - 3.5:.1f}% vs. 3.5% avg")
    with m2:
        st.metric("DSCR", f"{cf.dscr:.2f}",
                  delta="✓ covers debt" if cf.dscr >= 1.0 else "⚠ cashflow neg.")
    with m3:
        st.metric("Cashflow nach Steuer", f"€{cf.cashflow_nach_steuer_monthly:+.0f}/Monat")
    with m4:
        irr = cf.exit_yr11_free.irr_pct if cf.exit_yr11_free else 0.0
        st.metric("IRR 10yr (steuerfrei)", f"{irr:.1f}%")

    # ── Red flags ─────────────────────────────────────────────────────────────
    critical = report.critical_flags
    warnings = report.warning_flags
    if critical:
        st.divider()
        st.markdown(f"### 🔴 {len(critical)} Critical Issue{'s' if len(critical)>1 else ''}")
        for flag in critical:
            st.markdown(
                f'<div class="flag-critical"><strong>{flag.title}</strong><br>'
                f'{flag.description}<br><em>Mitigation: {flag.mitigation}</em></div>',
                unsafe_allow_html=True,
            )
    if warnings:
        st.markdown(f"### 🟡 {len(warnings)} Warning{'s' if len(warnings)>1 else ''}")
        for flag in warnings:
            st.markdown(
                f'<div class="flag-warning"><strong>{flag.title}</strong><br>'
                f'{flag.description}</div>',
                unsafe_allow_html=True,
            )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    st.divider()
    t1, t2, t3, t4 = st.tabs(["📊 Cashflow Model", "🏠 Property Facts", "📐 Assumptions", "📄 Sources"])

    with t1:
        _tab_cashflow(cf, listing)

    with t2:
        _tab_property_facts(listing, rent)

    with t3:
        _tab_assumptions(cf)

    with t4:
        _tab_sources(report)

    # ── Download ──────────────────────────────────────────────────────────────
    st.divider()
    if st.button("Generate PDF Report", type="primary"):
        try:
            import importlib, sys
            if 'immo2.reporting.pdf_generator' in sys.modules:
                importlib.reload(sys.modules['immo2.reporting.pdf_generator'])
            from immo2.reporting.pdf_generator import generate_pdf_sync
            pdf_bytes = generate_pdf_sync(report)
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name=f"immo2_{listing.plz}_{listing.stadt}.pdf",
                mime="application/pdf",
            )
        except Exception as e:
            st.error(f"PDF generation failed: {e}")


def _tab_cashflow(cf, listing):
    import pandas as pd
    import plotly.graph_objects as go

    # Summary metrics
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Acquisition**")
        ac = cf.acquisition
        st.write(f"Kaufpreis: **€{ac.kaufpreis:,.0f}**")
        st.write(f"Grunderwerbsteuer ({ac.grunderwerbsteuer_pct*100:.1f}%): €{ac.grunderwerbsteuer:,.0f}")
        st.write(f"Notar + Grundbuch: €{ac.notar_grundbuch:,.0f}")
        st.write(f"Makler: €{ac.makler:,.0f}")
        st.write(f"**Kaufnebenkosten gesamt: €{ac.kaufnebenkosten_total:,.0f}**")
        st.write(f"**Gesamtinvestition: €{ac.gesamtinvestition:,.0f}**")
    with col2:
        st.markdown("**Monthly (Year 1)**")
        st.write(f"Mieteinnahmen: +€{cf.miete_kalt_estimate:,.0f}")
        st.write(f"Zinsen: -€{cf.zinsen_monthly_year1:,.0f}")
        st.write(f"Tilgung: -€{cf.tilgung_monthly_year1:,.0f}")
        st.write(f"Hausgeld (deductible): -€{cf.hausgeld_deductible:,.0f}")
        st.write(f"Hausgeld (Rücklage): -€{cf.hausgeld_ruecklage:,.0f}")
        st.write(f"**Cashflow vor Steuer: {cf.cashflow_vor_steuer_monthly:+,.0f} €/Monat**")
        st.write(f"**Cashflow nach Steuer: {cf.cashflow_nach_steuer_monthly:+,.0f} €/Monat**")

    # 10-year cashflow chart
    if cf.rows:
        df = pd.DataFrame([{
            "Jahr": r.year,
            "Mieteinnahmen": r.miete_kalt,
            "Zinsen": -r.zinsen,
            "Hausgeld+NK": -(r.hausgeld_deductible + r.hausgeld_ruecklage + r.grundsteuer),
            "AfA-Steuereffekt": r.steuererstattung_estimate,
            "Cashflow nSt": r.cashflow_nach_steuer,
        } for r in cf.rows])

        fig = go.Figure()
        fig.add_trace(go.Bar(x=df["Jahr"], y=df["Cashflow nSt"], name="Cashflow nach Steuer",
                             marker_color=["#2E7D32" if v >= 0 else "#C62828" for v in df["Cashflow nSt"]]))
        fig.update_layout(title="Jährlicher Cashflow nach Steuer (10 Jahre)",
                          xaxis_title="Jahr", yaxis_title="€",
                          height=320, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # IRR scenarios
    st.markdown("**Exit Scenarios**")
    col_a, col_b = st.columns(2)
    if cf.exit_yr10_taxed:
        with col_a:
            e = cf.exit_yr10_taxed
            st.markdown(f"**Exit Jahr 10** (Spekulationssteuer fällig)")
            st.write(f"Verkaufspreis (angenommen): €{e.sale_price_assumed:,.0f}")
            st.write(f"Spekulationssteuer: €{e.spekulationssteuer:,.0f}")
            st.write(f"**IRR: {e.irr_pct:.1f}%**")
    if cf.exit_yr11_free:
        with col_b:
            e = cf.exit_yr11_free
            st.markdown(f"**Exit Jahr 11+** (steuerfrei)")
            st.write(f"Verkaufspreis (angenommen): €{e.sale_price_assumed:,.0f}")
            st.write(f"Spekulationssteuer: €0 (10-Jahres-Grenze überschritten)")
            st.write(f"**IRR: {e.irr_pct:.1f}%**")

    if cf.erhaltungsaufwand_flag:
        st.warning(
            f"⚠️ 15%-Regel: Geplante Renovierung €{cf.renovation_plan_amount:,.0f} "
            f"überschreitet Schwellenwert €{cf.erhaltungsaufwand_threshold:,.0f}. "
            f"Muss aktiviert werden (nicht sofort abzugsfähig)."
        )


def _tab_property_facts(listing, rent):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Property**")
        facts = {
            "Adresse": listing.address,
            "PLZ / Stadt": f"{listing.plz} {listing.stadt}",
            "Bundesland": listing.bundesland,
            "Wohnfläche": f"{listing.wohnflaeche_m2} m²" if listing.wohnflaeche_m2 else None,
            "Zimmer": listing.zimmer,
            "Baujahr": listing.baujahr,
            "Etage": listing.etage,
            "Aufzug": "Ja" if listing.aufzug else ("Nein" if listing.aufzug is False else "?"),
            "Balkon": "Ja" if listing.balkon else ("Nein" if listing.balkon is False else "?"),
        }
        for k, v in facts.items():
            if v is not None:
                st.write(f"**{k}**: {v}")
    with col2:
        st.markdown("**Energy & Condition**")
        facts2 = {
            "Energieklasse": listing.energieklasse,
            "Endenergiebedarf": f"{listing.endenergiebedarf_kwh} kWh/m²/Jahr" if listing.endenergiebedarf_kwh else None,
            "Heizungsart": listing.heizungsart,
            "Heizung Baujahr": listing.heizung_baujahr,
            "Zustand": listing.zustand,
        }
        for k, v in facts2.items():
            if v is not None:
                st.write(f"**{k}**: {v}")

        st.markdown("**Rent Estimate**")
        if rent and rent.city_in_corpus:
            st.write(f"Mietspiegel: **€{rent.per_m2_low:.2f}–€{rent.per_m2_high:.2f}/m²**")
            st.write(f"Gesamt: **€{rent.miete_kalt_low:,.0f}–€{rent.miete_kalt_high:,.0f}/Monat**")
            if rent.mietpreisbremse_applies:
                st.write(f"Mietpreisbremse: max. €{rent.mietpreisbremse_cap:,.0f}/Monat")
            if rent.source:
                st.caption(f"Quelle: {rent.source.name}")
        else:
            st.write("Mietspiegel: nicht verfügbar für diese Stadt (MVP: Berlin, München, Hamburg)")


def _tab_assumptions(cf):
    st.markdown("Every calculated value is based on these assumptions. Edit and recalculate to stress-test.")
    for k, v in cf.assumptions.items():
        st.write(f"**{k}**: {v}")
    st.info("To change assumptions: go back to the input form and adjust financing parameters.")


def _tab_sources(report: AnalysisReport):
    st.markdown("**Data sources used in this analysis:**")
    sources_shown = set()
    for src in report.sources:
        if src.name not in sources_shown:
            st.markdown(f"- **{src.name}** — {src.url or 'n/a'} (Date: {src.date}, Confidence: {src.confidence:.0%})")
            sources_shown.add(src.name)

    st.markdown(f"- **Mietspiegel** — source per city (see Rent Estimate tab)")
    st.markdown(f"- **Grunderwerbsteuer** — Finanzministerien der Länder (2025)")
    st.markdown(f"- **AfA-Regeln** — §7 EStG, §7b EStG")
    st.markdown(f"- **GEG 2024** — Gebäudeenergiegesetz")
    st.markdown(f"- **KfW BEG** — kfw.de (rates as of 2025-12)")

    st.divider()
    st.caption(
        "⚠️ This analysis is a **decision support tool** only. All outputs require independent "
        "verification before investment decisions. This is not financial or legal advice. "
        "Immo2 assumes no liability for decisions based on this report. "
        "Data sources: OpenStreetMap contributors (ODbL), Zensus 2022 Statistisches Bundesamt (dl-de/by-2-0), "
        "Bundesbank, respective Mietspiegels."
    )
    if listing := report.listing:
        st.caption(f"Analysis generated: {report.created_at.strftime('%Y-%m-%d %H:%M')} UTC | Job: {report.job_id}")


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────
def main():
    if "page" not in st.session_state:
        st.session_state["page"] = "input"

    page = st.session_state["page"]

    if page == "input":
        page_input()
    elif page == "loading":
        page_loading()
    elif page == "review":
        page_review()
    elif page == "dashboard":
        page_dashboard()
    else:
        page_input()


if __name__ == "__main__":
    main()
