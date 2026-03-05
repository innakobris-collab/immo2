"""
Agent 2 — Exposé Extraction.
Uses Claude Sonnet 4.6 with strict extraction rules.
NEVER infers missing values — returns null for anything not explicitly stated.
"""
from __future__ import annotations
import json
import re
from datetime import datetime
from ..models.listing import RawListing, ExtractedListing
from ..config import settings


EXTRACTION_SYSTEM_PROMPT = """\
Du bist ein präziser Datenextraktions-Assistent für deutsche Immobilien-Exposés.

REGELN (NICHT VERHANDELBAR):
1. Extrahiere NUR Werte, die EXPLIZIT im Text stehen. NIEMALS schätzen, ableiten oder erfinden.
2. Wenn ein Feld NICHT IM TEXT steht: gib null zurück.
3. NIEMALS aus Kontext schlussfolgern: z.B. "Altbau" ist KEIN Baujahr. "gute Lage" ist KEINE Energieklasse.
4. Zahlen: Extrahiere nur wenn eindeutig dem Feld zugeordnet. "350" allein ist keine Kaufpreis-Angabe.
5. Bundesland: Leite aus PLZ oder Stadtname ab WENN eindeutig. Sonst null.
6. Energieklasse: Nur offizielle Klassen (A+, A, B, C, D, E, F, G, H). "gut gedämmt" ist KEINE Energieklasse.
7. Kaufpreis: Kaufpreis/Angebotspreis in €. NICHT Mietpreis. NICHT Hausgeld.

Antworte NUR mit einem validen JSON-Objekt. Keine Erklärungen.
"""

EXTRACTION_USER_TEMPLATE = """\
Extrahiere alle verfügbaren Immobiliendaten aus folgendem Exposé-Text:

---
{raw_text}
---

Gib folgendes JSON zurück:
{{
  "address": "Straße Nummer, PLZ Stadt" oder null,
  "plz": "5-stellige PLZ" oder null,
  "stadt": "Stadtname" oder null,
  "stadtteil": "Stadtteil/Bezirk" oder null,
  "bundesland": "Bundesland" oder null,
  "wohnflaeche_m2": Zahl oder null,
  "zimmer": Zahl (z.B. 3.5) oder null,
  "baujahr": Ganzzahl oder null,
  "etage": Ganzzahl oder null,
  "gesamtgeschosse": Ganzzahl oder null,
  "grundstueck_m2": Zahl oder null,
  "aufzug": true/false oder null,
  "balkon": true/false oder null,
  "keller": true/false oder null,
  "stellplatz": true/false oder null,
  "kaufpreis": Zahl in € oder null,
  "hausgeld_total": monatliches Hausgeld in € oder null,
  "grundsteuer_annual": jährliche Grundsteuer in € oder null,
  "ist_miete_kalt": aktuelle Kaltmiete pro Monat in € (nur bei vermieteten Objekten) oder null,
  "energieklasse": "A+/A/B/C/D/E/F/G/H" oder null,
  "endenergiebedarf_kwh": Endenergiebedarf in kWh/m²/Jahr oder null,
  "heizungsart": "Gas/Öl/Fernwärme/Wärmepumpe/etc." oder null,
  "heizung_baujahr": Baujahr der Heizungsanlage als Ganzzahl oder null,
  "zustand": "Kurzbeschreibung des Zustands" oder null,
  "letztes_renovierungsjahr": Ganzzahl oder null,
  "weg_anzahl_einheiten": Anzahl Wohneinheiten in der WEG oder null,
  "extraction_confidence": Zahl zwischen 0.0 und 1.0 (Gesamtvertrauen in die Extraktion),
  "missing_fields": ["Liste", "der", "Felder", "die", "fehlen", "aber", "wichtig", "wären"],
  "red_flags": ["Auffälligkeiten", "die", "direkt", "im", "Text", "stehen"]
}}
"""


async def extract_listing(raw_listing: RawListing) -> ExtractedListing:
    """Extract structured listing data from raw text using Claude Sonnet 4.6."""
    import anthropic

    if not raw_listing.raw_text or len(raw_listing.raw_text.strip()) < 50:
        return ExtractedListing(
            source_url=raw_listing.source_url,
            source_type=raw_listing.source_type,
            fetched_at=raw_listing.fetched_at,
            extraction_confidence=0.0,
            missing_fields=["raw_text"],
            red_flags=["Kein Text extrahiert — bitte PDF erneut hochladen oder manuell eingeben."],
        )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    user_content = EXTRACTION_USER_TEMPLATE.format(
        raw_text=raw_listing.raw_text[:15000],  # cap at 15K chars
    )

    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    response_text = message.content[0].text.strip()

    # Parse JSON — robust extraction
    extracted_data = _parse_json_response(response_text)
    if extracted_data is None:
        return ExtractedListing(
            source_url=raw_listing.source_url,
            source_type=raw_listing.source_type,
            fetched_at=raw_listing.fetched_at,
            extraction_confidence=0.0,
            missing_fields=["parse_error"],
            red_flags=["JSON-Parsing fehlgeschlagen — bitte Exposé-Text prüfen."],
        )

    # Build ExtractedListing from parsed data
    listing = _build_listing(extracted_data, raw_listing)

    # Geocode if address found and no lat/lon
    if listing.address and listing.lat is None:
        listing.lat, listing.lon = await _geocode(listing.address)

    return listing


def _parse_json_response(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Strip markdown code block if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        # Try to find JSON object in text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def _build_listing(data: dict, raw: RawListing) -> ExtractedListing:
    """Build ExtractedListing Pydantic model from parsed dict."""
    def safe_float(v) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def safe_int(v) -> int | None:
        if v is None:
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    def safe_bool(v) -> bool | None:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "ja", "yes", "1")
        return None

    return ExtractedListing(
        address=data.get("address"),
        plz=str(data["plz"]) if data.get("plz") else None,
        stadt=data.get("stadt"),
        stadtteil=data.get("stadtteil"),
        bundesland=data.get("bundesland"),
        wohnflaeche_m2=safe_float(data.get("wohnflaeche_m2")),
        zimmer=safe_float(data.get("zimmer")),
        baujahr=safe_int(data.get("baujahr")),
        etage=safe_int(data.get("etage")),
        gesamtgeschosse=safe_int(data.get("gesamtgeschosse")),
        grundstueck_m2=safe_float(data.get("grundstueck_m2")),
        aufzug=safe_bool(data.get("aufzug")),
        balkon=safe_bool(data.get("balkon")),
        keller=safe_bool(data.get("keller")),
        stellplatz=safe_bool(data.get("stellplatz")),
        kaufpreis=safe_float(data.get("kaufpreis")),
        kaufpreis_per_m2=(
            safe_float(data.get("kaufpreis")) / safe_float(data.get("wohnflaeche_m2"))
            if data.get("kaufpreis") and data.get("wohnflaeche_m2") else None
        ),
        hausgeld_total=safe_float(data.get("hausgeld_total")),
        grundsteuer_annual=safe_float(data.get("grundsteuer_annual")),
        ist_miete_kalt=safe_float(data.get("ist_miete_kalt")),
        energieklasse=data.get("energieklasse"),
        endenergiebedarf_kwh=safe_float(data.get("endenergiebedarf_kwh")),
        heizungsart=data.get("heizungsart"),
        heizung_baujahr=safe_int(data.get("heizung_baujahr")),
        zustand=data.get("zustand"),
        letztes_renovierungsjahr=safe_int(data.get("letztes_renovierungsjahr")),
        weg_anzahl_einheiten=safe_int(data.get("weg_anzahl_einheiten")),
        extraction_confidence=safe_float(data.get("extraction_confidence")) or 0.5,
        missing_fields=data.get("missing_fields") or [],
        red_flags=data.get("red_flags") or [],
        source_url=raw.source_url,
        source_type=raw.source_type,
        fetched_at=raw.fetched_at,
    )


async def _geocode(address: str) -> tuple[float | None, float | None]:
    """Geocode a German address using Nominatim (free, ODbL)."""
    try:
        import httpx
        params = {
            "q": address + ", Deutschland",
            "format": "json",
            "limit": 1,
            "countrycodes": "de",
        }
        headers = {"User-Agent": settings.nominatim_user_agent}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers=headers,
                timeout=10.0,
            )
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass
    return None, None
