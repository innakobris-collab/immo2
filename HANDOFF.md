# Immo2 — Full Handoff Document
*For new Claude chat: read this file completely before starting work.*

---

## MESSAGE FROM ANDRE (for new chat)

Hey Claude, I'm building a German real estate AI platform for buy-to-rent investors.
I've already done a full research project (4 waves, ~160 web searches, red team audited)
and built a working MVP. This file contains:
1. Everything we researched about the German PropTech market and building this product
2. Full summary of what's already built (immo2 MVP)
3. Key German law facts the cashflow engine depends on

Please read everything carefully. Find what's useful and either add it to the existing
codebase or help me build the next similar project using the same research base.
The live app is at: https://8ufqpywpugcqk4tr746wpp.streamlit.app/
The GitHub repo is: https://github.com/innakobris-collab/immo2

---

## PART 1 — WHAT'S ALREADY BUILT (immo2 MVP)

### Status: LIVE AND DEPLOYED (March 2026)

**Live URL**: https://8ufqpywpugcqk4tr746wpp.streamlit.app/
**GitHub**: https://github.com/innakobris-collab/immo2
**Local path**: `c:\Users\Andre\Documents\immo2\`

### Stack
- **LLM**: Claude Sonnet 4.6 (extraction + analysis)
- **UI**: Streamlit (deployed on Streamlit Community Cloud)
- **PDF generation**: Playwright headless Chromium (sync API)
- **Database**: SQLite (MVP); PostgreSQL planned for V1
- **Python**: 3.12, pyproject.toml, src layout

### What the app does
1. User uploads a PDF exposé, pastes a URL, or manually enters listing data
2. Claude Sonnet 4.6 extracts 50+ structured fields (address, Kaufpreis, Wohnfläche, Baujahr, Hausgeld, Energieklasse, etc.)
3. German cashflow engine calculates: acquisition costs, monthly cashflow, DSCR, IRR, AfA tax effect, Spekulationssteuer, 10-year projections
4. Mietspiegel lookup provides rent estimate for 31 cities (Berlin, Munich, Hamburg + 28 more inline + all 16 Bundesländer as fallback)
5. Red flags engine flags GEG risks, 15% renovation rule, negative cashflow, etc.
6. Deal score (0–100) with pros/cons
7. PDF report download via Playwright

### Architecture (4 modules, sequential)
```
Intake → Extract (Claude Sonnet) → Cashflow (deterministic Python) → Report (Jinja2 + Playwright)
```

### Key files
```
frontend/app.py                          — Streamlit UI (all pages)
src/immo2/agents/pipeline.py             — Main analysis pipeline
src/immo2/agents/agent2_extract.py       — Claude Sonnet extraction prompt
src/immo2/cashflow/engine.py             — German cashflow engine
src/immo2/cashflow/german_tax.py         — AfA, Grunderwerbsteuer, Spekulationssteuer
src/immo2/cashflow/financing.py          — Mortgage, DSCR
src/immo2/cashflow/irr.py                — 10yr IRR calculation
src/immo2/cashflow/red_flags.py          — Risk flag engine
src/immo2/cashflow/scoring.py            — Deal score 0–100
src/immo2/rag/mietspiegel_stubs.py       — Rent estimates (31 cities + Bundesland fallback)
src/immo2/reporting/pdf_generator.py     — Playwright PDF generation
src/immo2/data/grunderwerbsteuer.json    — All 16 Bundesländer rates
src/immo2/data/afa_rules.json            — AfA depreciation rules
src/immo2/data/mietspiegel/              — Berlin, Munich, Hamburg JSON tables
tests/test_cashflow.py                   — 19 unit tests (all pass)
tests/test_extraction_accuracy.py        — Evaluation harness (10 labeled fixtures)
tests/fixtures/labeled_listings.json     — Ground truth for accuracy testing
```

### Tests
- 21 tests pass (19 cashflow unit tests + 2 non-API harness tests)
- 2 API tests skip without ANTHROPIC_API_KEY
- Target: ≥85% extraction accuracy on critical fields (not yet measured with real API)

### Known issues / tech debt
- PDF generation on Streamlit Cloud: untested (Playwright sync API implemented but cloud behavior unknown)
- Mietspiegel data: 31 cities covered; all others use Bundesland fallback (medium confidence)
- URL tab: IS24 blocks bots; recommend users use Manual tab instead
- Extraction accuracy: not yet measured end-to-end

### To run locally
```bash
cd c:\Users\Andre\Documents\immo2
cp .env.example .env  # add ANTHROPIC_API_KEY
pip install -e .
playwright install chromium
streamlit run frontend/app.py
```

### Environment
- ANTHROPIC_API_KEY required in .env
- Streamlit Cloud secrets: ANTHROPIC_API_KEY set in dashboard

---

## PART 2 — DEEP RESEARCH: GERMAN REAL ESTATE AI MARKET

### 2.1 The Opportunity (confirmed gap)

Germany has ~17 million rental apartments, vacancy <1% in major cities.
**No product exists** combining all of:
- Automated German exposé extraction (LLM)
- Micro-location scoring (transit, noise, flood, POI)
- Rent estimate cross-referenced to official Mietspiegel
- Photo-based condition assessment
- Full German cashflow model (AfA, Hausgeld, Grunderwerbsteuer, KfW)
- Multi-dimensional risk scoring (GEG, WEG, Mieterschutz, flood)
- Source-grounded investor report

This gap is confirmed. Every existing tool is either US-focused, institutional-only, or covers only one piece.

### 2.2 Market Size
- Germany PropTech: $2.13B (2024) → $12.72B (2035), CAGR 17.6%
- AI PropTech VC: +42% annualized in 2025
- Berlin: €180M PropTech funding in 2024 (EU #1 city)
- German RE transactions: €34.3B in 2024 (+21% YoY)
- ~15M German adults with >€100K investable assets = addressable market

### 2.3 Competitive Landscape

**AVM / Valuation:**
- **PriceHubble** (CH) — best EU multi-country AVM, explainable AI, B2B (banks)
- **Sprengnetter** (DE, now Scout24 75%) — 9B+ data points, largest DE AVM
- **empirica regio** (DE) — independent; contract rents + buying prices; REST API; 400 districts
- **GREIX** (DE) — free quarterly reports; real notarized transaction data back to 1960
- **Value AG** (DE) — B2B only

**Deal Analysis (NO German product exists):**
- Cactus, UWmatic, DealWorthIt, Built AI — all US-focused, no German tax/WEG logic
- Hypofriend (DE) — finance-only calculator, no full analysis
- propwise.de / ohana-invest.de — basic static calculators, no AI

**Competitor to watch: Scout24 BuyerPlus** — opportunity analysis for buyers/investors. Limited but a signal.

**Active German PropTech startups 2024–2026:**
- Buena (Berlin, €49M) — property management digitization
- Enter (Berlin, €40M) — energy efficiency platform
- Predium (Munich, €13M) — AI ESG/decarbonization for portfolios
- vivanta (Berlin, €2.5M) — AI property management WEG + rental
- Lystio (Vienna, €500K) — AI-native listing portal, relevance-ranked

**Strategic threat: Scout24 data monopoly**
Scout24 has acquired: Sprengnetter (AVM) + bulwiengesa (commercial data) + 21st Real Estate (analysis) + NeuBau Kompass + Exploreal + Flowfact/Propstack (CRM) + Fotocasa/Habitaclia (Spain, Mar 2026, €153M). Controls Germany's #1 listing portal + largest AVM + commercial RE data.
**Implication**: Any platform must either partner with Scout24 OR build entirely on alternative sources (RWI-GEO-RED, government data, Zensus 2022, IS24 official API).

### 2.4 Data Sources

**Listing data:**
- IS24 Official API (api.immobilienscout24.de) — licensed, pay-per-use
- RWI-GEO-RED (FDZ@rwi-essen.de) — IS24 data for research; free; apply now (3–6 months)
- Immowelt API (AVIV/KKR) — contact partner@immowelt.de
- OpenImmo XML — German standard for portal data exchange (300 fields)

**Rent data:**
- City Mietspiegel PDFs (all cities >50k must publish since 2022)
- empirica regio API — best independent rent index, quarterly, contract rents, 400 districts
- mietenwatch API (GitHub) — Berlin only, 2017/2019 data, open-source architecture

**Official free data (all usable):**
- BORIS-D — Bodenrichtwerte (land values) all Germany, WFS/REST, annual
- Destatis GENESIS — housing prices, construction, income; REST API
- Zensus 2022 — 24.2M responses, building/dwelling level data, 100m grid cells
- BBSR/INKAR — housing market classification, urban stats
- GREIX — real transaction prices from Gutachterausschüsse, 2M+ deals back to 1960
- EEA Noise Maps — EU noise maps, WMS
- LAWA Flood Maps — state-level flood risk zones
- BKA Kriminalstatistik — crime statistics (Kreis level)
- Zensus 2022 — vacancy, year built, net rent at grid level

**Location/mapping:**
- Overpass API (OSM) — free, full Germany POI/transit coverage
- OpenRouteService — free walk-time isochrones, routing
- HERE Maps — best EU geocoding (German company), commercial
- BORIS-D WFS — land values per parcel

**Building/energy:**
- syte.ms ENERsyte — energy class estimation for 22M+ German buildings, commercial API
- Nexiga — 300+ features per building, LoD2 3D models, Zensus integration
- DIBt (Energieausweis registry) — NOT public

**Finance/macro:**
- Deutsche Bundesbank API — mortgage rates, ECB rate
- KfW BEG — loan rates (2.27–2.93% effective), grants up to 70% for heating
- Hypofriend — current DE mortgage benchmark: 3.71% Dec 2025

**Computer vision:**
- restb.ai — best-in-class PropTech CV, 700 data points/photo, condition C1–C6, <500ms
  → Email to verify Germany coverage + startup pricing
- hellodata.ai — newer alternative

---

## PART 3 — GERMAN LAW (CRITICAL FOR CASHFLOW MODEL)

### 3.1 Grunderwerbsteuer (by Bundesland 2025)
| Bundesland | Rate |
|---|---|
| Bayern, Sachsen | 3.5% |
| Baden-Württemberg, Niedersachsen, Sachsen-Anhalt, Rheinland-Pfalz, Thüringen, Bremen | 5.0% |
| Berlin, Hessen, Mecklenburg-Vorpommern | 6.0% |
| Hamburg | 5.5% |
| Brandenburg, NRW, Saarland, Schleswig-Holstein | 6.5% |

### 3.2 AfA — Depreciation
- Standard (Baujahr 1925+): **2%/year** over 50 years
- Old (pre-1925): **2.5%/year** over 40 years
- Neubau (completed after 31.12.2022): **3%/year** over 33.3 years
- Sonder-AfA §7b (Bauantrag Jan 2023 – Sept 30, 2030): **+5%/year** first 4 years; limit €4,000/m²; construction cost limit €5,200/m²
- Degressive AfA §7(5a) (Bauantrag Oct 2023 – Sept 2029): **5–6% of residual book value/year**; can switch to linear anytime
- Land value CANNOT be depreciated (typically 20–30% Grundanteil in urban areas)

### 3.3 Spekulationssteuer
- Sale within 10 years: profit taxed at personal income tax rate (14–45%)
- Sale after 10 years: **completely tax-free**
- Exception: owner-occupied in year of sale + 2 preceding years → always tax-free
- Start date = notarized Kaufvertragsdatum

### 3.4 Mietpreisbremse
- Active in 410+ municipalities
- Cap: max +10% above ortsübliche Vergleichsmiete (Mietspiegel)
- Extended until 31 December 2029 (CDU/CSU+SPD coalition, Dec 2024)
- Indexmietverträge in distressed markets: capped at max +3.5%/year
- Exemptions: Neubau completed after 1 October 2014; first let after Kernsanierung

### 3.5 GEG 2024 (Heating Law)
- Every newly installed heating must run ≥65% renewable energy
- Cities >100K: mandatory from 1 July 2026
- Cities <100K: from 1 July 2028
- Existing boilers: run until failure (no forced replacement)
- Modernization rent increase: up to 10% of costs/year, max €0.50/m²/month within 6yr
- KfW grants: up to 70% of heating replacement costs (base 30% + Climate Speed Bonus 20% + Income Bonus 20%)

### 3.6 15% Rule (anschaffungsnaher Herstellungsaufwand)
- Renovation within 3 years post-purchase > 15% of Gebäudeanteil → must capitalize ALL renovation costs
- Critical risk for distressed property buyers
- Threshold: 15% × (Kaufpreis × Gebäudeanteil %)

### 3.7 Hausgeld
- Monthly WEG fee: typically €2.50–€5.50/m²/month
- ~60–70% is tax-deductible (Verwaltung, Versicherung, Instandhaltungsanteile)
- Instandhaltungsrücklage itself is NOT deductible (separate line item)

### 3.8 Kaufnebenkosten
- Grunderwerbsteuer: 3.5–6.5% (by Bundesland)
- Notar + Grundbuch: ~1.5–2.0%
- Makler: 3.0–3.57% buyer side for investment properties (2020 reform = owner-occupied only)
- Total typical: **7–12% of Kaufpreis**

### 3.9 Verlustverrechnung
- Rental losses offset employment income in same year (no ring-fencing)
- Loss carryforward: 70% of remaining income/year (2024–2027); returns to 60% in 2028
- Result: new investors often get tax refund in early years (high AfA + negative cashflow)

### 3.10 WEG Reform 2020 (key for ETW buyers)
- Simple majority now sufficient for modernization approvals
- Quorum requirement eliminated
- Hybrid Eigentümerversammlungen legal
- Zertifizierter Verwalter required (IHK exam, since 2023)
- Due diligence: last 3 years WEG protocols + Jahresabrechnungen + Rücklage balance

### 3.11 EU AI Act
- Real estate valuation AI may be classified high-risk (Annex III)
- Compliance deadline: 2 August 2026
- Safe framing: "decision support tool" with human oversight, not automated decision-maker

---

## PART 4 — AI/ML MODEL RECOMMENDATIONS

### 4.1 LLM Strategy
- **Claude Sonnet 4.6** — PRIMARY: 1M token context, 89% accuracy on math fields, $3/M input tokens. <$1/deal
- **Claude Haiku 4.5** — SECONDARY: 80% cost reduction for simple classification tasks
- **Batch API**: 50% discount for non-time-critical processing
- **Prompt caching**: Cache system prompts + Mietspiegel RAG context

### 4.2 AVM / Rent Model
- XGBoost/LightGBM — industry standard for tabular RE data, MAPE 10–15%
- Feature importance for Germany: Wohnfläche > Lage (lat/lon, H3) > PLZ/Stadtteil > Baujahr > Bodenrichtwert > Energieklasse > Hausgeld > Zimmer > Aufzug/Balkon
- Training data: RWI-GEO-RED (apply: FDZ@rwi-essen.de, 3–6 months wait)
- Uncertainty quantification: Conformal prediction (MAPIE library) — valid 90% CI
- Geographically Weighted Regression for explainability

### 4.3 Agent Framework (V1)
- **LangGraph 1.0** (Oct 2025) — production-ready, durable execution, PostgresSaver checkpointing
- Pattern: outer LangGraph state machine + parallel fan-out for independent agents
- Monitoring: Langfuse (LLM tracing + evals)
- Model monitoring: Evidently AI (drift detection)

### 4.4 RAG Architecture (V1)
- Ingest: OCR all city Mietspiegel PDFs (65+ cities)
- Embed: voyage-3-large (Anthropic) or text-embedding-3-large (OpenAI)
- Store: pgvector (same PostgreSQL DB — simpler than Qdrant at MVP scale)
- Retrieve: Hybrid search (vector + BM25)
- This Mietspiegel RAG corpus is a defensible proprietary asset

### 4.5 Location Scoring
- Build proprietary walkability score from OSM (WalkScore not available in Germany)
- Overpass API: POI query within 500m/1km radius
- OpenRouteService: walk-time isochrones (5/10/15 min)
- Pre-compute for all H3 resolution-9 hexagons in Germany (~2.4M cells)
- Data layers: BORIS-D (land values), EEA (noise), LAWA (flood), BKA (crime)

---

## PART 5 — FULL TECH STACK (RECOMMENDED)

### MVP (what's built)
```
LLM:           Claude Sonnet 4.6
UI:            Streamlit
PDF:           Playwright (headless Chromium, sync API)
DB:            SQLite (in-memory for reports)
Backend:       FastAPI (also built, not used in UI)
Deployment:    Streamlit Community Cloud
```

### V1 (next phase)
```
LLM:           Claude Sonnet 4.6 + Haiku 4.5
Agent:         LangGraph 1.0 + PostgresSaver
DB:            PostgreSQL 16 + PostGIS + pgvector
ML:            XGBoost (rent model, trained on RWI-GEO-RED)
CV:            restb.ai API (photo condition assessment)
Geocoding:     HERE Maps (or Nominatim free tier)
Location:      Overpass API + OpenRouteService + BORIS-D WFS
Frontend:      Next.js + Tailwind (replace Streamlit)
Maps:          Leaflet / Mapbox
Deployment:    Docker + fly.io (EU regions)
Monitoring:    Langfuse + Evidently AI
Pipeline:      Prefect (data refresh)
```

---

## PART 6 — PRODUCT ROADMAP

### MVP ✓ (DONE)
- Intake (PDF + URL + manual)
- Claude Sonnet extraction
- German cashflow engine
- Mietspiegel stubs (31 cities + 16 Bundesländer fallback)
- Red flags + deal scoring
- PDF report (Playwright)
- Streamlit UI deployed

### V1 (Months 1–3 from now)
- Location intelligence (Overpass + BORIS-D + noise + flood)
- XGBoost rent model (needs RWI-GEO-RED data — apply NOW)
- Photo analysis (restb.ai)
- Full risk scoring (7 dimensions)
- Market context (Destatis + Bundesbank)
- IS24 official API integration
- PostgreSQL + PostGIS + pgvector
- Next.js frontend (replace Streamlit)
- Extraction accuracy validation (≥85% target, not yet measured)

### V2 (Months 4–6)
- Full Mietspiegel RAG corpus (65+ cities OCR'd)
- H3 pre-computed location cache
- WG-Zimmer yield analysis
- KfW subsidy calculator integration
- Multi-property portfolio analysis

### Pending actions (do now)
1. Email FDZ@rwi-essen.de — apply for RWI-GEO-RED academic data (3–6 month wait, start clock)
2. Email restb.ai — verify Germany coverage + startup pricing
3. Run extraction accuracy test: `pytest tests/test_extraction_accuracy.py -v` (needs ANTHROPIC_API_KEY)
4. Get 5 beta users (share live URL)

---

## PART 7 — GERMAN MARKET CONTEXT (2026)

### Market conditions
- Price recovery: +3–4% forecast 2026; prices bottomed mid-2024
- Rents: +3–5%/year; contract rents growing fastest in eastern Germany
- Construction: falling to 185K–215K completions (massive supply gap vs 400K target)
- Vacancy: <1% in all 7 major cities
- Mortgage rates: 3.71% (Dec 2025, 10yr fixed); ECB expected to cut in 2026
- Buyer's market in some segments; seller's market for good locations

### Best investment cities by gross yield (2025 data)
| City | Avg price €/m² | Gross yield | Notes |
|---|---|---|---|
| Chemnitz | ~1,200 | 6–8% | Highest yield; population risk |
| Magdeburg | ~1,500 | 5–6% | Good yields; vacancy risk |
| Halle | ~1,500 | 5–6% | Similar to Magdeburg |
| Leipzig | ~2,800 | 4.5–5% | Best East German market; growing fast |
| Dortmund/Essen | ~2,000 | 4–5% | NRW industrial cities |
| Berlin | ~4,200 | 3–4% | Low yield; capital appreciation |
| Munich | ~8,500 | 2.5–3% | Near impossible for positive cashflow |
| Hamburg | ~6,000 | 3–3.5% | |

### Key risks for investors
1. **GEG compliance**: Energieklasse G/H buildings = stranded asset risk post-2026/2028
2. **Mietpreisbremse**: limits rent increases to Mietspiegel +10% in 410+ municipalities
3. **15% renovation rule**: critical for distressed buys (must model explicitly)
4. **Leerstandsrisiko**: eastern German cities with population decline
5. **Zinsbindung risk**: rising rates if ECB reverses cuts
6. **WEG Sonderumlage**: hidden risk — check Instandhaltungsrücklage balance

---

## PART 8 — NOTES ON RENT ESTIMATION (IMPORTANT)

**Use contract rents (Vertragsmieten), NOT asking rents (Angebotsmieten).**
Asking rents run 10–20% above achievable contract rents in hot markets (Berlin, Munich, Hamburg).
The Mietspiegel shows ortsübliche Vergleichsmiete = achievable contract rent range.

**Mietspiegel coverage in current immo2:**
- Full city-level tables: Berlin (2023), Munich (2024), Hamburg (2023) + 28 inline cities
- Bundesland fallback for all 16 states (medium confidence, ±15% range)
- Missing: Full RAG corpus (65+ cities OCR'd) — planned for V1

**Mietpreisbremse cities (partial list):**
Berlin, Hamburg, Munich, Frankfurt, Cologne, Stuttgart, Düsseldorf, Leipzig, Dresden, Hannover, Nuremberg, Bonn, Freiburg, Münster, Karlsruhe, Mannheim, Mainz, Erfurt, Rostock, Kiel, Aachen, Wuppertal, Bielefeld, Bochum, Bremen, Wiesbaden — and 400+ smaller municipalities.
**No Mietpreisbremse**: Essen, Duisburg, Magdeburg, Halle, Chemnitz (low-rent markets).

---

## PART 9 — ARCHITECTURE DECISIONS & RATIONALE

**Why sequential pipeline, not LangGraph for MVP:**
LangGraph adds complexity (checkpointing, state machines) that isn't needed when pipeline is linear.
MVP = Intake → Extract → Cashflow → Report. No parallel fan-out needed until V1.

**Why Playwright for PDF, not WeasyPrint:**
WeasyPrint requires GTK3/libgobject (fails on Windows without complex setup).
Playwright uses headless Chromium — works everywhere, native HTML rendering, no system deps.

**Why Mietspiegel stubs, not ML model:**
No labeled training data available yet (need RWI-GEO-RED). Mietspiegel = legally binding
ortsübliche Vergleichsmiete = more trustworthy than a model anyway. ML rent model for V1.

**Why no AVM (price estimation):**
No ground truth for sold prices in Germany (Gutachterausschüsse data not freely available at scale).
Position immo2 as cashflow tool, not valuation tool. GREIX data available quarterly but lagged.

**Why Streamlit (not Next.js) for MVP:**
Speed of iteration. Can prototype in hours. Switch to Next.js for V1 once product-market fit confirmed.

**Why SQLite (not PostgreSQL) for MVP:**
Zero ops overhead. Reports stored in-memory (routes.py). PostgreSQL + pgvector for V1 when
persistent storage + vector search needed.

---

*End of handoff document. Generated 2026-03-14.*
