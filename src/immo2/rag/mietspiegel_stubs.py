"""
Mietspiegel lookup — MVP stub using hardcoded city JSON tables.
Returns rent ranges based on Baujahr + Wohnlage.
V1: Replace with pgvector RAG over 65+ city OCR corpus.
"""
from __future__ import annotations
import json
from pathlib import Path
from ..models.report import RentEstimate, Source

_DATA_DIR = Path(__file__).parent.parent / "data" / "mietspiegel"

# City slug → JSON filename + display name + source
_CITY_MAP = {
    "berlin": ("berlin_2023.json", "Berlin", "2023"),
    "münchen": ("munich_2024.json", "München", "2024"),
    "munich": ("munich_2024.json", "München", "2024"),
    "muenchen": ("munich_2024.json", "München", "2024"),
    "hamburg": ("hamburg_2023.json", "Hamburg", "2023"),
}


def _load(filename: str) -> dict:
    path = _DATA_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _map_baujahr_to_key(baujahr: int | None, city_data: dict) -> str | None:
    """Map Baujahr integer to the correct table key for the city."""
    table = city_data.get("table", {})
    keys = list(table.keys())

    if baujahr is None:
        return keys[0] if keys else None  # default to oldest bucket

    # Common Berlin-style keys
    mapping = [
        ("vor_1918", None, 1917),
        ("vor_1919", None, 1918),
        ("1918_1949", 1918, 1949),
        ("1919_1948", 1919, 1948),
        ("1949_1965", 1949, 1965),
        ("1950_1964", 1950, 1964),
        ("1965_1972", 1965, 1972),
        ("1966_1977", 1966, 1977),
        ("1961_1977", 1961, 1977),
        ("1973_1990", 1973, 1990),
        ("1978_1989", 1978, 1989),
        ("1978_1990", 1978, 1990),
        ("1991_2002", 1991, 2002),
        ("1990_1999", 1990, 1999),
        ("2000_2013", 2000, 2013),
        ("2003_2013", 2003, 2013),
        ("ab_2014", 2014, None),
    ]

    for key, year_from, year_to in mapping:
        if key not in table:
            continue
        low = year_from if year_from else 0
        high = year_to if year_to else 9999
        if low <= baujahr <= high:
            return key

    # Fallback: return last key (most recent)
    return keys[-1] if keys else None


def _infer_wohnlage(stadtteil: str | None, city: str) -> str:
    """Very rough Wohnlage inference from Stadtteil name.
    Returns "einfach", "mittel", or "gut".
    V1: Replace with PostGIS Wohnlage layer lookup.
    """
    if stadtteil is None:
        return "mittel"

    st = stadtteil.lower()

    gut_keywords = [
        "mitte", "prenzlauer", "friedrichshain", "charlottenburg", "wilmersdorf",
        "schwabing", "maxvorstadt", "altstadt", "lehel", "bogenhausen",
        "harvestehude", "rotherbaum", "eimsbüttel", "blankenese",
        "westend", "sachsenhausen", "bornheim", "nordend",
    ]
    einfach_keywords = [
        "marzahn", "hellersdorf", "spandau", "reinickendorf",
        "neuperlach", "ramersdorf", "hasenbergl",
        "billstedt", "wilhelmsburg", "steilshoop",
        "fechenheim", "zeilsheim", "griesheim",
    ]

    if any(k in st for k in gut_keywords):
        return "gut"
    if any(k in st for k in einfach_keywords):
        return "einfach"
    return "mittel"


def get_mietspiegel_estimate(
    stadt: str | None,
    baujahr: int | None,
    wohnflaeche_m2: float,
    stadtteil: str | None = None,
    wohnlage_override: str | None = None,
) -> RentEstimate:
    """Return Mietspiegel rent estimate for a property.
    All values in €/month total (not per m²).
    """
    if stadt is None:
        return RentEstimate(
            miete_kalt_low=0.0, miete_kalt_mid=0.0, miete_kalt_high=0.0,
            per_m2_low=0.0, per_m2_mid=0.0, per_m2_high=0.0,
            city_in_corpus=False,
            notes="Stadt nicht erkannt — manuelle Mieteingabe erforderlich.",
        )

    city_key = stadt.lower().strip()
    city_info = _CITY_MAP.get(city_key)

    if city_info is None:
        return RentEstimate(
            miete_kalt_low=0.0, miete_kalt_mid=0.0, miete_kalt_high=0.0,
            per_m2_low=0.0, per_m2_mid=0.0, per_m2_high=0.0,
            city_in_corpus=False,
            notes=f"'{stadt}' nicht im Mietspiegel-Korpus (MVP: Berlin, München, Hamburg). "
                  "Manuelle Mieteingabe erforderlich.",
        )

    filename, city_display, year = city_info
    city_data = _load(filename)

    baujahr_key = _map_baujahr_to_key(baujahr, city_data)
    wohnlage = wohnlage_override or _infer_wohnlage(stadtteil, city_key)

    table = city_data.get("table", {})
    if not baujahr_key or baujahr_key not in table:
        return RentEstimate(
            miete_kalt_low=0.0, miete_kalt_mid=0.0, miete_kalt_high=0.0,
            per_m2_low=0.0, per_m2_mid=0.0, per_m2_high=0.0,
            city_in_corpus=True,
            notes=f"Baujahr {baujahr} konnte nicht zugeordnet werden.",
        )

    row = table[baujahr_key].get(wohnlage)
    if not row:
        # Fallback to mittel
        row = table[baujahr_key].get("mittel", {"low": 0, "mid": 0, "high": 0})

    low_m2 = row["low"]
    mid_m2 = row["mid"]
    high_m2 = row["high"]

    mpb = city_data.get("mietpreisbremse", {})
    mpb_applies = mpb.get("applies", False)
    mpb_cap = mid_m2 * mpb.get("cap_multiplier", 1.10) if mpb_applies else None
    neubau_exempt_from = mpb.get("neubau_exempt_from", 2014)
    neubau_exempt = bool(baujahr and baujahr >= neubau_exempt_from)

    if neubau_exempt:
        mpb_applies = False
        mpb_cap = None

    source = Source(
        name=f"Mietspiegel {city_display} {year}",
        url=city_data.get("_url", ""),
        date=city_data.get("_valid_from", year),
        confidence=0.85,
        raw_value=f"{baujahr_key} / {wohnlage}: €{low_m2}–€{high_m2}/m²",
    )

    return RentEstimate(
        miete_kalt_low=round(low_m2 * wohnflaeche_m2, 0),
        miete_kalt_mid=round(mid_m2 * wohnflaeche_m2, 0),
        miete_kalt_high=round(high_m2 * wohnflaeche_m2, 0),
        per_m2_low=low_m2,
        per_m2_mid=mid_m2,
        per_m2_high=high_m2,
        mietpreisbremse_applies=mpb_applies,
        mietpreisbremse_cap=round(mpb_cap * wohnflaeche_m2, 0) if mpb_cap else None,
        neubau_exempt=neubau_exempt,
        source=source,
        city_in_corpus=True,
        notes=(
            f"Mietspiegel {city_display} {year}, {baujahr_key.replace('_', ' ')}, "
            f"Wohnlage: {wohnlage}. "
            + ("Mietpreisbremse gilt: max. Vergleichsmiete +10%. " if mpb_applies else "")
            + ("Neubau-Ausnahme: Mietpreisbremse gilt nicht (Baujahr ≥2014). " if neubau_exempt else "")
        ),
    )
