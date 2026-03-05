"""
Rule-based red flag detection. All deterministic.
Returns RedFlag objects — no LLM involved here.
"""
from __future__ import annotations
from ..models.report import RedFlag


def check_energy_class(energieklasse: str | None, baujahr: int | None) -> list[RedFlag]:
    flags: list[RedFlag] = []
    if energieklasse is None:
        flags.append(RedFlag(
            severity="warning",
            category="energy",
            title="Energieklasse unbekannt",
            description="Energieklasse nicht im Exposé angegeben. Energieausweis vor Kauf anfordern.",
            mitigation="Energieausweis (Verbrauchs- oder Bedarfsausweis) beim Verkäufer anfordern.",
            source="GEG 2024 — Pflichtangabe in Inseraten seit 2014",
        ))
        return flags

    ek = energieklasse.upper().strip()
    if ek in ("G", "H"):
        flags.append(RedFlag(
            severity="critical",
            category="energy",
            title=f"Energieklasse {ek} — Hochrisiko-Stranded-Asset",
            description=(
                f"Energieklasse {ek} bedeutet sehr hohen Energieverbrauch und hohes Risiko als "
                f"'Stranded Asset'. Mieter zahlen hohe Nebenkosten → Vermietbarkeit sinkt. "
                f"Bei Heizungsausfall: GEG-Pflicht (≥65% erneuerbar) sofort fällig."
            ),
            mitigation=(
                "Vollsanierungskosten kalkulieren. KfW BEG Förderprogramme prüfen (bis 70% Zuschuss). "
                "Nur kaufen wenn Sanierungskosten im Kaufpreis reflektiert sind."
            ),
            source="GEG 2024; EU Gebäuderichtlinie (EPBD)",
        ))
    elif ek in ("E", "F"):
        flags.append(RedFlag(
            severity="warning",
            category="energy",
            title=f"Energieklasse {ek} — GEG-Sanierungsrisiko",
            description=(
                f"Energieklasse {ek}: erhöhter Energieverbrauch. "
                f"Heizungsersatz wird GEG-pflichtig (≥65% erneuerbar) wenn Heizung ausfällt. "
                f"Städte >100K Einwohner: ab 01.07.2026; kleinere Gemeinden: ab 01.07.2028."
            ),
            mitigation="Baujahr Heizungsanlage prüfen. KfW BEG Zuschuss einkalkulieren (30–50%). "
                       "Restlebensdauer Heizung schätzen lassen.",
            source="GEG §71 (2024)",
        ))
    elif ek in ("C", "D"):
        flags.append(RedFlag(
            severity="info",
            category="energy",
            title=f"Energieklasse {ek} — Mittelmäßige Energieeffizienz",
            description=(
                f"Energieklasse {ek}: solide Effizienz, aber Verbesserungspotential vorhanden. "
                f"Langfristig könnte Modernisierung die Vermietbarkeit verbessern."
            ),
            mitigation="Heizungsanlage und Dämmung prüfen. Optional: iSFP erstellen lassen für +5% KfW-Bonus.",
            source="GEG 2024",
        ))

    return flags


def check_baujahr(baujahr: int | None) -> list[RedFlag]:
    flags: list[RedFlag] = []
    if baujahr is None:
        flags.append(RedFlag(
            severity="warning",
            category="structure",
            title="Baujahr unbekannt",
            description="Baujahr nicht angegeben. Beeinflusst AfA, Schadstoffe, GEG-Risiko.",
            mitigation="Baujahr aus Grundbuch, Baugenehmigung oder Teilungserklärung ermitteln.",
        ))
        return flags

    if baujahr < 1919:
        flags.append(RedFlag(
            severity="info",
            category="structure",
            title="Gründerzeitbau (vor 1919)",
            description="Typisch hohe Deckenhöhen, Altbaucharme — aber erhöhter Instandhaltungsaufwand. AfA 2.5%/Jahr.",
            mitigation="Baugutachter beauftragen. Dach, Fassade, Leitungen prüfen.",
        ))

    if baujahr < 1978:
        flags.append(RedFlag(
            severity="warning",
            category="structure",
            title="Asbestrisiko (Baujahr vor 1978/1994)",
            description=(
                f"Baujahr {baujahr}: Asbest war bis 1993 in Deutschland legal. "
                f"Mögliche Vorkommen: Dachplatten, Fassadenplatten (Eternit), Bodenbeläge (Vinylplatten), "
                f"Rohrisolierungen, Fensterbänke, Spachtelmassen."
            ),
            mitigation=(
                "Asbestgutachten im Rahmen Baugutachten beauftragen. "
                "Bei Renovierungsplanung: Asbestprobenernahme VOR Beginn. "
                "Entsorgungskosten können erheblich sein (€5K–€50K+)."
            ),
            source="GefStoffV; TRGS 519",
        ))

    if baujahr < 1973:
        flags.append(RedFlag(
            severity="warning",
            category="structure",
            title="Bleirohre möglich (Baujahr vor 1973)",
            description=(
                f"Baujahr {baujahr}: Bleileitungen in Trinkwasserinstallation waren bis ~1972 üblich. "
                f"Seit 2013 gilt EU-Grenzwert 10 μg/l — Eigentümer haftet für Einhaltung."
            ),
            mitigation="Trinkwasserinstallation von Klempner prüfen lassen. Bleileitungssanierung: €3K–€15K.",
            source="Trinkwasserverordnung §17; DIN 50930-6",
        ))

    return flags


def check_mietpreisbremse(
    plz: str | None,
    stadt: str | None,
    baujahr: int | None,
    ist_neubau_post_2014: bool = False,
) -> list[RedFlag]:
    """Check if Mietpreisbremse likely applies. Uses city name heuristic for MVP.
    V1: use full 410-municipality CSV lookup.
    """
    flags: list[RedFlag] = []

    # Neubau post-2014 is exempt
    if baujahr and baujahr >= 2014:
        flags.append(RedFlag(
            severity="info",
            category="legal",
            title="Mietpreisbremse-Ausnahme: Neubau",
            description=f"Baujahr {baujahr} ≥ 2014: Mietpreisbremse gilt NICHT (§556e BGB Neubau-Ausnahme).",
            mitigation="Marktmiete frei setzbar. Prüfen ob auch Erstvermietung nach umfassender Sanierung vorliegt.",
            source="§556e Abs.1 BGB; Mietrechtsanpassungsgesetz 2019",
        ))
        return flags

    # Major cities where Mietpreisbremse is known to apply
    mpb_cities = {
        "berlin", "münchen", "munich", "hamburg", "frankfurt", "köln", "cologne",
        "stuttgart", "düsseldorf", "dortmund", "essen", "bremen", "hannover",
        "nürnberg", "nuremberg", "duisburg", "bochum", "wuppertal", "bielefeld",
        "bonn", "münster", "karlsruhe", "mannheim", "augsburg", "wiesbaden",
        "freiburg", "heidelberg", "mainz", "erfurt", "rostock", "potsdam",
        "darmstadt", "regensburg", "ingolstadt", "würzburg", "ulm",
    }

    city_lower = (stadt or "").lower()
    if any(city in city_lower for city in mpb_cities):
        flags.append(RedFlag(
            severity="info",
            category="legal",
            title="Mietpreisbremse wahrscheinlich anwendbar",
            description=(
                "Diese Stadt liegt wahrscheinlich in einem Gebiet mit angespanntem Wohnungsmarkt. "
                "Neue Mietverträge: max. ortsübliche Vergleichsmiete + 10%. "
                "Verlängerung bis 31.12.2029 (Koalitionsvertrag CDU/SPD 2025). "
                "Indexmietverträge: max. +3.5%/Jahr."
            ),
            mitigation=(
                "Exakte PLZ gegen aktuelle Mietpreisbremse-Verordnung des Bundeslandes prüfen. "
                "Mietspiegel-Vergleichsmiete als Ausgangswert für maximale Miete nutzen."
            ),
            source="§556d BGB; Verlängerung Dez 2024 bis 31.12.2029",
        ))

    return flags


def check_15pct_rule(
    renovation_plan_eur: float,
    threshold_eur: float,
) -> list[RedFlag]:
    flags: list[RedFlag] = []
    if renovation_plan_eur <= 0:
        return flags

    if renovation_plan_eur >= threshold_eur:
        flags.append(RedFlag(
            severity="critical",
            category="financial",
            title=f"15%-Regel ausgelöst: Sanierungskosten müssen aktiviert werden",
            description=(
                f"Geplante Renovierung (€{renovation_plan_eur:,.0f}) überschreitet "
                f"den Schwellenwert von €{threshold_eur:,.0f} (= 15% des Gebäudeanteils). "
                f"Folge: ALLE Renovierungskosten in den ersten 3 Jahren nach Kauf müssen als "
                f"'anschaffungsnaher Herstellungsaufwand' aktiviert und über die Restnutzungsdauer "
                f"abgeschrieben werden — NICHT sofort abziehbar. "
                f"Der prognostizierte sofortige Steuereffekt entfällt."
            ),
            mitigation=(
                "Renovierung auf Zeiträume >3 Jahre nach Kaufdatum aufteilen OR "
                "Kaufpreis entsprechend anpassen OR "
                "Renovierungsumfang unter den Schwellenwert reduzieren."
            ),
            source="§6 Abs.1 Nr.1a EStG (anschaffungsnaher Herstellungsaufwand)",
        ))
    elif renovation_plan_eur >= threshold_eur * 0.75:
        flags.append(RedFlag(
            severity="warning",
            category="financial",
            title=f"15%-Regel Warnung: Renovierung nähert sich dem Schwellenwert",
            description=(
                f"Geplante Renovierung (€{renovation_plan_eur:,.0f}) entspricht "
                f"{renovation_plan_eur / threshold_eur * 100:.0f}% des Schwellenwerts (€{threshold_eur:,.0f}). "
                f"Bei weiteren Renovierungskosten in den ersten 3 Jahren: 15%-Grenze überschritten."
            ),
            mitigation="Alle Sanierungsmaßnahmen in den ersten 3 Jahren sorgfältig dokumentieren.",
            source="§6 Abs.1 Nr.1a EStG",
        ))

    return flags


def check_geg_heater_risk(
    energieklasse: str | None,
    heizung_baujahr: int | None,
    current_year: int = 2026,
) -> list[RedFlag]:
    flags: list[RedFlag] = []
    if heizung_baujahr is None:
        return flags

    heater_age = current_year - heizung_baujahr
    typical_lifespan = 20  # years for gas/oil boiler

    if heater_age >= 15 and energieklasse and energieklasse.upper() in ("D", "E", "F", "G", "H"):
        estimated_years_remaining = max(0, typical_lifespan - heater_age)
        flags.append(RedFlag(
            severity="warning",
            category="energy",
            title=f"GEG-Risiko: Heizung Baujahr {heizung_baujahr} ({heater_age} Jahre alt)",
            description=(
                f"Heizungsanlage Baujahr {heizung_baujahr} (ca. {heater_age} Jahre alt). "
                f"Geschätzte Restlebensdauer: ~{estimated_years_remaining} Jahre. "
                f"Bei Ausfall: Ersatz muss ≥65% erneuerbare Energien nutzen (GEG §71). "
                f"Geschätzte Kosten: €12.000–€25.000 (je nach System). "
                f"KfW BEG EM Zuschuss bis 70% verfügbar."
            ),
            mitigation=(
                f"Heizungsanlage begutachten lassen. "
                f"KfW BEG EM Zuschuss bereits jetzt beantragen (Antrag VOR Beauftragung). "
                f"Bei freiwilligem Austausch bis 2028: Climate Speed Bonus +20% noch nutzbar."
            ),
            source="GEG §71 (2024); KfW BEG EM Programm 458",
        ))

    return flags


def check_dscr(dscr: float) -> list[RedFlag]:
    flags: list[RedFlag] = []
    if dscr < 1.0:
        flags.append(RedFlag(
            severity="critical",
            category="financial",
            title=f"DSCR {dscr:.2f} — Mieteinnahmen decken Schuldendienst NICHT",
            description=(
                f"Schuldendienstdeckungsgrad (DSCR) = {dscr:.2f}. "
                f"Die Mieteinnahmen reichen nicht aus, um Zins und Tilgung zu bedienen. "
                f"Laufende Zuzahlung aus Eigenmitteln erforderlich."
            ),
            mitigation="Eigenkapitalanteil erhöhen ODER Kaufpreis neu verhandeln ODER Mietpotential prüfen.",
        ))
    elif dscr < 1.20:
        flags.append(RedFlag(
            severity="warning",
            category="financial",
            title=f"DSCR {dscr:.2f} — Geringe Deckungsreserve",
            description=(
                f"DSCR = {dscr:.2f}. Mietausfall oder Zinssteigerung kann schnell zu negativem "
                f"Cashflow führen. Bankstandard: DSCR ≥ 1.20."
            ),
            mitigation="Instandhaltungsrücklage prüfen. Mietvertrag und Mieterbonität verifizieren.",
        ))
    return flags


def run_all_checks(
    energieklasse: str | None = None,
    baujahr: int | None = None,
    heizung_baujahr: int | None = None,
    stadt: str | None = None,
    plz: str | None = None,
    renovation_plan_eur: float = 0.0,
    threshold_15pct: float = 0.0,
    dscr: float = 1.5,
) -> list[RedFlag]:
    """Run all red flag checks and return sorted list (critical first)."""
    flags: list[RedFlag] = []
    flags.extend(check_energy_class(energieklasse, baujahr))
    flags.extend(check_baujahr(baujahr))
    flags.extend(check_mietpreisbremse(plz, stadt, baujahr))
    flags.extend(check_geg_heater_risk(energieklasse, heizung_baujahr))
    flags.extend(check_15pct_rule(renovation_plan_eur, threshold_15pct))
    flags.extend(check_dscr(dscr))

    # Sort: critical → warning → info
    order = {"critical": 0, "warning": 1, "info": 2}
    flags.sort(key=lambda f: order.get(f.severity, 3))
    return flags
