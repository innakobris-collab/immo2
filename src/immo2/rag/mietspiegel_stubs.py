"""
Mietspiegel lookup — MVP stub covering 30+ German cities + Bundesland fallback.
All rent values are contract rents (Vertragsmieten), ~10-15% below asking rents.
V1: Replace with pgvector RAG over 65+ city OCR corpus.
"""
from __future__ import annotations
import json
from pathlib import Path
from ..models.report import RentEstimate, Source

_DATA_DIR = Path(__file__).parent.parent / "data" / "mietspiegel"

# ── Cities stored as separate JSON files ─────────────────────────────────────
_JSON_CITY_MAP = {
    "berlin": ("berlin_2023.json", "Berlin", "2023"),
    "münchen": ("munich_2024.json", "München", "2024"),
    "munich": ("munich_2024.json", "München", "2024"),
    "muenchen": ("munich_2024.json", "München", "2024"),
    "hamburg": ("hamburg_2023.json", "Hamburg", "2023"),
}

# ── Inline city data (contract rents €/m²/month, Kaltmiete) ──────────────────
# Sources: empirica regio, JLL/Savills market reports, city Mietspiegels 2023/2024
# Baujahr keys: vor_1949 | 1949_1969 | 1970_1990 | 1991_2009 | ab_2010
_INLINE_CITIES: dict[str, dict] = {
    "köln": {
        "_display": "Köln", "_year": "2024",
        "_url": "https://www.stadt-koeln.de/leben-in-koeln/wohnen/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.0, "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
            "1949_1969": {"einfach": {"low": 7.5, "mid": 9.0,  "high": 11.0}, "mittel": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "gut": {"low": 10.5, "mid": 12.5, "high": 15.0}},
            "1970_1990": {"einfach": {"low": 8.0, "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.5}},
            "1991_2009": {"einfach": {"low": 9.0, "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 15.0}, "gut": {"low": 12.5, "mid": 15.0, "high": 18.0}},
            "ab_2010":   {"einfach": {"low": 11.0,"mid": 13.0, "high": 15.5}, "mittel": {"low": 13.0, "mid": 15.5, "high": 18.5}, "gut": {"low": 15.5, "mid": 18.5, "high": 22.0}},
        },
    },
    "frankfurt": {
        "_display": "Frankfurt am Main", "_year": "2024",
        "_url": "https://www.frankfurt.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 9.5,  "mid": 11.5, "high": 14.0}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.5}, "gut": {"low": 13.5, "mid": 16.0, "high": 19.5}},
            "1949_1969": {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 15.0}, "gut": {"low": 12.0, "mid": 14.5, "high": 17.5}},
            "1970_1990": {"einfach": {"low": 9.0,  "mid": 11.0, "high": 13.5}, "mittel": {"low": 11.0, "mid": 13.0, "high": 15.5}, "gut": {"low": 12.5, "mid": 15.0, "high": 18.0}},
            "1991_2009": {"einfach": {"low": 10.5, "mid": 12.5, "high": 15.0}, "mittel": {"low": 12.5, "mid": 15.0, "high": 18.0}, "gut": {"low": 14.5, "mid": 17.5, "high": 21.0}},
            "ab_2010":   {"einfach": {"low": 13.0, "mid": 15.5, "high": 18.5}, "mittel": {"low": 15.5, "mid": 18.5, "high": 22.0}, "gut": {"low": 18.5, "mid": 22.0, "high": 26.0}},
        },
    },
    "stuttgart": {
        "_display": "Stuttgart", "_year": "2023",
        "_url": "https://www.stuttgart.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.0}, "gut": {"low": 13.0, "mid": 15.5, "high": 18.5}},
            "1949_1969": {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.0, "mid": 14.5, "high": 17.0}},
            "1970_1990": {"einfach": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "mittel": {"low": 11.0, "mid": 13.0, "high": 15.0}, "gut": {"low": 12.5, "mid": 15.0, "high": 17.5}},
            "1991_2009": {"einfach": {"low": 10.5, "mid": 12.5, "high": 14.5}, "mittel": {"low": 12.5, "mid": 14.5, "high": 17.0}, "gut": {"low": 14.0, "mid": 16.5, "high": 19.5}},
            "ab_2010":   {"einfach": {"low": 12.5, "mid": 15.0, "high": 18.0}, "mittel": {"low": 15.0, "mid": 17.5, "high": 21.0}, "gut": {"low": 17.0, "mid": 20.0, "high": 24.0}},
        },
    },
    "düsseldorf": {
        "_display": "Düsseldorf", "_year": "2024",
        "_url": "https://www.duesseldorf.de/wohnen/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.0, "mid": 14.0, "high": 16.5}},
            "1949_1969": {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.5}},
            "1970_1990": {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.0, "mid": 14.0, "high": 16.5}},
            "1991_2009": {"einfach": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.0}, "gut": {"low": 13.0, "mid": 15.5, "high": 18.5}},
            "ab_2010":   {"einfach": {"low": 11.5, "mid": 13.5, "high": 16.0}, "mittel": {"low": 13.5, "mid": 16.0, "high": 19.0}, "gut": {"low": 16.0, "mid": 19.0, "high": 22.5}},
        },
    },
    "leipzig": {
        "_display": "Leipzig", "_year": "2023",
        "_url": "https://www.leipzig.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1949_1969": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1970_1990": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1991_2009": {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "ab_2010":   {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
        },
    },
    "dortmund": {
        "_display": "Dortmund", "_year": "2023",
        "_url": "https://www.dortmund.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1949_1969": {"einfach": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "mittel": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "gut": {"low": 9.0,  "mid": 10.5, "high": 12.5}},
            "1970_1990": {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1991_2009": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "gut": {"low": 10.5, "mid": 12.5, "high": 14.5}},
            "ab_2010":   {"einfach": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.5, "mid": 14.5, "high": 17.0}},
        },
    },
    "essen": {
        "_display": "Essen", "_year": "2023",
        "_url": "https://www.essen.de/mietspiegel",
        "mietpreisbremse": {"applies": False, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "mittel": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "gut": {"low": 9.0,  "mid": 10.5, "high": 12.5}},
            "1949_1969": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1970_1990": {"einfach": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "mittel": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "gut": {"low": 9.0,  "mid": 10.5, "high": 12.5}},
            "1991_2009": {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "gut": {"low": 10.0, "mid": 11.5, "high": 13.5}},
            "ab_2010":   {"einfach": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "mittel": {"low": 10.0, "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
        },
    },
    "bremen": {
        "_display": "Bremen", "_year": "2024",
        "_url": "https://www.bremen.de/wohnen/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "gut": {"low": 10.5, "mid": 12.5, "high": 14.5}},
            "1949_1969": {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.0, "high": 12.0}, "gut": {"low": 10.0, "mid": 12.0, "high": 14.0}},
            "1970_1990": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "gut": {"low": 10.5, "mid": 12.5, "high": 14.5}},
            "1991_2009": {"einfach": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "mittel": {"low": 10.0, "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
            "ab_2010":   {"einfach": {"low": 10.0, "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.0}, "gut": {"low": 13.5, "mid": 16.0, "high": 19.0}},
        },
    },
    "dresden": {
        "_display": "Dresden", "_year": "2023",
        "_url": "https://www.dresden.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "gut": {"low": 9.5,  "mid": 11.5, "high": 13.5}},
            "1949_1969": {"einfach": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "mittel": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "gut": {"low": 9.0,  "mid": 10.5, "high": 12.5}},
            "1970_1990": {"einfach": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "mittel": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "gut": {"low": 9.0,  "mid": 10.5, "high": 12.5}},
            "1991_2009": {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "gut": {"low": 10.0, "mid": 11.5, "high": 13.5}},
            "ab_2010":   {"einfach": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "mittel": {"low": 10.0, "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
        },
    },
    "hannover": {
        "_display": "Hannover", "_year": "2023",
        "_url": "https://www.hannover.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "gut": {"low": 10.5, "mid": 12.5, "high": 14.5}},
            "1949_1969": {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.0, "high": 12.0}, "gut": {"low": 10.0, "mid": 12.0, "high": 14.0}},
            "1970_1990": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "gut": {"low": 10.5, "mid": 12.5, "high": 14.5}},
            "1991_2009": {"einfach": {"low": 8.5,  "mid": 10.0, "high": 12.0}, "mittel": {"low": 10.0, "mid": 12.0, "high": 14.0}, "gut": {"low": 12.0, "mid": 14.0, "high": 16.5}},
            "ab_2010":   {"einfach": {"low": 10.0, "mid": 12.0, "high": 14.0}, "mittel": {"low": 12.0, "mid": 14.0, "high": 16.5}, "gut": {"low": 14.0, "mid": 16.5, "high": 19.5}},
        },
    },
    "nürnberg": {
        "_display": "Nürnberg", "_year": "2023",
        "_url": "https://www.nuernberg.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.5}},
            "1949_1969": {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "gut": {"low": 10.5, "mid": 12.5, "high": 15.0}},
            "1970_1990": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.5}},
            "1991_2009": {"einfach": {"low": 8.5,  "mid": 10.0, "high": 12.0}, "mittel": {"low": 10.0, "mid": 12.0, "high": 14.5}, "gut": {"low": 12.0, "mid": 14.5, "high": 17.5}},
            "ab_2010":   {"einfach": {"low": 10.0, "mid": 12.0, "high": 14.5}, "mittel": {"low": 12.0, "mid": 14.5, "high": 17.5}, "gut": {"low": 14.5, "mid": 17.5, "high": 21.0}},
        },
    },
    "duisburg": {
        "_display": "Duisburg", "_year": "2023",
        "_url": "https://www.duisburg.de/mietspiegel",
        "mietpreisbremse": {"applies": False, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 5.5,  "mid": 6.5,  "high": 8.0},  "mittel": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "gut": {"low": 8.0,  "mid": 9.5,  "high": 11.0}},
            "1949_1969": {"einfach": {"low": 5.0,  "mid": 6.5,  "high": 8.0},  "mittel": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "gut": {"low": 8.0,  "mid": 9.5,  "high": 11.0}},
            "1970_1990": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1991_2009": {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "ab_2010":   {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "mittel": {"low": 9.5,  "mid": 11.0, "high": 13.0}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.0}},
        },
    },
    "bochum": {
        "_display": "Bochum", "_year": "2023",
        "_url": "https://www.bochum.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1949_1969": {"einfach": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "mittel": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "gut": {"low": 9.0,  "mid": 10.5, "high": 12.5}},
            "1970_1990": {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1991_2009": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "gut": {"low": 10.5, "mid": 12.5, "high": 14.5}},
            "ab_2010":   {"einfach": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.5, "mid": 14.5, "high": 17.0}},
        },
    },
    "bonn": {
        "_display": "Bonn", "_year": "2024",
        "_url": "https://www.bonn.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.5, "mid": 14.5, "high": 17.0}},
            "1949_1969": {"einfach": {"low": 8.0,  "mid": 10.0, "high": 12.0}, "mittel": {"low": 10.0, "mid": 12.0, "high": 14.0}, "gut": {"low": 12.0, "mid": 14.0, "high": 16.5}},
            "1970_1990": {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.5, "mid": 14.5, "high": 17.0}},
            "1991_2009": {"einfach": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.0}, "gut": {"low": 13.5, "mid": 16.0, "high": 19.0}},
            "ab_2010":   {"einfach": {"low": 11.5, "mid": 13.5, "high": 16.0}, "mittel": {"low": 13.5, "mid": 16.0, "high": 19.0}, "gut": {"low": 16.0, "mid": 19.0, "high": 22.5}},
        },
    },
    "freiburg": {
        "_display": "Freiburg im Breisgau", "_year": "2023",
        "_url": "https://www.freiburg.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 15.5}, "gut": {"low": 13.0, "mid": 15.5, "high": 18.0}},
            "1949_1969": {"einfach": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "mittel": {"low": 11.0, "mid": 13.0, "high": 15.0}, "gut": {"low": 12.5, "mid": 15.0, "high": 17.5}},
            "1970_1990": {"einfach": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 15.5}, "gut": {"low": 13.0, "mid": 15.5, "high": 18.0}},
            "1991_2009": {"einfach": {"low": 10.5, "mid": 12.5, "high": 15.0}, "mittel": {"low": 12.5, "mid": 15.0, "high": 17.5}, "gut": {"low": 14.5, "mid": 17.5, "high": 20.5}},
            "ab_2010":   {"einfach": {"low": 12.5, "mid": 15.0, "high": 17.5}, "mittel": {"low": 15.0, "mid": 17.5, "high": 21.0}, "gut": {"low": 17.5, "mid": 21.0, "high": 25.0}},
        },
    },
    "augsburg": {
        "_display": "Augsburg", "_year": "2023",
        "_url": "https://www.augsburg.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
            "1949_1969": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 11.0}, "mittel": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.5}},
            "1970_1990": {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
            "1991_2009": {"einfach": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "mittel": {"low": 11.0, "mid": 13.0, "high": 15.5}, "gut": {"low": 13.0, "mid": 15.5, "high": 18.5}},
            "ab_2010":   {"einfach": {"low": 11.0, "mid": 13.0, "high": 15.5}, "mittel": {"low": 13.0, "mid": 15.5, "high": 18.5}, "gut": {"low": 15.5, "mid": 18.5, "high": 22.0}},
        },
    },
    "wiesbaden": {
        "_display": "Wiesbaden", "_year": "2024",
        "_url": "https://www.wiesbaden.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 15.0}, "gut": {"low": 12.5, "mid": 15.0, "high": 17.5}},
            "1949_1969": {"einfach": {"low": 8.0,  "mid": 10.0, "high": 12.0}, "mittel": {"low": 10.0, "mid": 12.0, "high": 14.5}, "gut": {"low": 12.0, "mid": 14.5, "high": 17.0}},
            "1970_1990": {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 15.0}, "gut": {"low": 12.5, "mid": 15.0, "high": 17.5}},
            "1991_2009": {"einfach": {"low": 9.5,  "mid": 11.5, "high": 14.0}, "mittel": {"low": 11.5, "mid": 14.0, "high": 16.5}, "gut": {"low": 14.0, "mid": 16.5, "high": 19.5}},
            "ab_2010":   {"einfach": {"low": 11.5, "mid": 14.0, "high": 16.5}, "mittel": {"low": 14.0, "mid": 16.5, "high": 20.0}, "gut": {"low": 16.5, "mid": 20.0, "high": 24.0}},
        },
    },
    "münster": {
        "_display": "Münster", "_year": "2023",
        "_url": "https://www.muenster.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.5, "mid": 14.5, "high": 17.0}},
            "1949_1969": {"einfach": {"low": 8.0,  "mid": 10.0, "high": 12.0}, "mittel": {"low": 10.0, "mid": 12.0, "high": 14.0}, "gut": {"low": 12.0, "mid": 14.0, "high": 16.5}},
            "1970_1990": {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.5, "mid": 14.5, "high": 17.0}},
            "1991_2009": {"einfach": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.0}, "gut": {"low": 13.5, "mid": 16.0, "high": 19.0}},
            "ab_2010":   {"einfach": {"low": 11.5, "mid": 13.5, "high": 16.0}, "mittel": {"low": 13.5, "mid": 16.0, "high": 19.0}, "gut": {"low": 16.0, "mid": 19.0, "high": 22.5}},
        },
    },
    "karlsruhe": {
        "_display": "Karlsruhe", "_year": "2023",
        "_url": "https://www.karlsruhe.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.0, "mid": 14.0, "high": 16.5}},
            "1949_1969": {"einfach": {"low": 8.0,  "mid": 10.0, "high": 12.0}, "mittel": {"low": 10.0, "mid": 12.0, "high": 14.0}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
            "1970_1990": {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.0, "mid": 14.0, "high": 16.5}},
            "1991_2009": {"einfach": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.0}, "gut": {"low": 13.0, "mid": 15.5, "high": 18.5}},
            "ab_2010":   {"einfach": {"low": 11.5, "mid": 13.5, "high": 16.0}, "mittel": {"low": 13.5, "mid": 16.0, "high": 19.0}, "gut": {"low": 15.5, "mid": 18.5, "high": 22.0}},
        },
    },
    "mannheim": {
        "_display": "Mannheim", "_year": "2023",
        "_url": "https://www.mannheim.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
            "1949_1969": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 11.0}, "mittel": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.5}},
            "1970_1990": {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
            "1991_2009": {"einfach": {"low": 9.0,  "mid": 11.0, "high": 13.0}, "mittel": {"low": 11.0, "mid": 13.0, "high": 15.5}, "gut": {"low": 13.0, "mid": 15.5, "high": 18.5}},
            "ab_2010":   {"einfach": {"low": 10.5, "mid": 12.5, "high": 15.0}, "mittel": {"low": 12.5, "mid": 15.0, "high": 18.0}, "gut": {"low": 15.0, "mid": 18.0, "high": 21.5}},
        },
    },
    "mainz": {
        "_display": "Mainz", "_year": "2024",
        "_url": "https://www.mainz.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 15.0}, "gut": {"low": 12.5, "mid": 15.0, "high": 17.5}},
            "1949_1969": {"einfach": {"low": 8.0,  "mid": 10.0, "high": 12.0}, "mittel": {"low": 10.0, "mid": 12.0, "high": 14.5}, "gut": {"low": 12.0, "mid": 14.5, "high": 17.0}},
            "1970_1990": {"einfach": {"low": 8.5,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 15.0}, "gut": {"low": 12.5, "mid": 15.0, "high": 17.5}},
            "1991_2009": {"einfach": {"low": 9.5,  "mid": 11.5, "high": 14.0}, "mittel": {"low": 11.5, "mid": 14.0, "high": 16.5}, "gut": {"low": 14.0, "mid": 16.5, "high": 19.5}},
            "ab_2010":   {"einfach": {"low": 11.5, "mid": 14.0, "high": 16.5}, "mittel": {"low": 14.0, "mid": 16.5, "high": 20.0}, "gut": {"low": 16.5, "mid": 20.0, "high": 24.0}},
        },
    },
    "erfurt": {
        "_display": "Erfurt", "_year": "2023",
        "_url": "https://www.erfurt.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "mittel": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "gut": {"low": 9.0,  "mid": 10.5, "high": 12.5}},
            "1949_1969": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1970_1990": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1991_2009": {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "ab_2010":   {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
        },
    },
    "magdeburg": {
        "_display": "Magdeburg", "_year": "2023",
        "_url": "https://www.magdeburg.de/mietspiegel",
        "mietpreisbremse": {"applies": False, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 5.0,  "mid": 6.5,  "high": 8.0},  "mittel": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "gut": {"low": 8.0,  "mid": 9.5,  "high": 11.0}},
            "1949_1969": {"einfach": {"low": 4.5,  "mid": 6.0,  "high": 7.5},  "mittel": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "gut": {"low": 7.5,  "mid": 9.0,  "high": 10.5}},
            "1970_1990": {"einfach": {"low": 4.5,  "mid": 6.0,  "high": 7.5},  "mittel": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "gut": {"low": 7.5,  "mid": 9.0,  "high": 10.5}},
            "1991_2009": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "ab_2010":   {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "gut": {"low": 10.0, "mid": 11.5, "high": 13.5}},
        },
    },
    "halle": {
        "_display": "Halle (Saale)", "_year": "2023",
        "_url": "https://www.halle.de/mietspiegel",
        "mietpreisbremse": {"applies": False, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 5.0,  "mid": 6.5,  "high": 8.0},  "mittel": {"low": 6.5,  "mid": 7.5,  "high": 9.0},  "gut": {"low": 7.5,  "mid": 9.0,  "high": 10.5}},
            "1949_1969": {"einfach": {"low": 4.5,  "mid": 5.5,  "high": 7.0},  "mittel": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "gut": {"low": 7.0,  "mid": 8.5,  "high": 10.0}},
            "1970_1990": {"einfach": {"low": 4.5,  "mid": 5.5,  "high": 7.0},  "mittel": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "gut": {"low": 7.0,  "mid": 8.5,  "high": 10.0}},
            "1991_2009": {"einfach": {"low": 5.5,  "mid": 6.5,  "high": 8.0},  "mittel": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "gut": {"low": 8.0,  "mid": 9.5,  "high": 11.0}},
            "ab_2010":   {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "gut": {"low": 10.0, "mid": 11.5, "high": 13.0}},
        },
    },
    "chemnitz": {
        "_display": "Chemnitz", "_year": "2023",
        "_url": "https://www.chemnitz.de/mietspiegel",
        "mietpreisbremse": {"applies": False, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 4.5,  "mid": 6.0,  "high": 7.5},  "mittel": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "gut": {"low": 7.5,  "mid": 9.0,  "high": 10.5}},
            "1949_1969": {"einfach": {"low": 4.0,  "mid": 5.5,  "high": 7.0},  "mittel": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "gut": {"low": 7.0,  "mid": 8.5,  "high": 10.0}},
            "1970_1990": {"einfach": {"low": 4.0,  "mid": 5.5,  "high": 7.0},  "mittel": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "gut": {"low": 7.0,  "mid": 8.5,  "high": 10.0}},
            "1991_2009": {"einfach": {"low": 5.0,  "mid": 6.5,  "high": 8.0},  "mittel": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "gut": {"low": 8.0,  "mid": 9.5,  "high": 11.0}},
            "ab_2010":   {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
        },
    },
    "rostock": {
        "_display": "Rostock", "_year": "2023",
        "_url": "https://www.rostock.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1949_1969": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1970_1990": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1991_2009": {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "ab_2010":   {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.5}, "mittel": {"low": 9.5,  "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
        },
    },
    "kiel": {
        "_display": "Kiel", "_year": "2023",
        "_url": "https://www.kiel.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.0}, "gut": {"low": 10.0, "mid": 11.5, "high": 13.5}},
            "1949_1969": {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1970_1990": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.0}, "gut": {"low": 10.0, "mid": 11.5, "high": 13.5}},
            "1991_2009": {"einfach": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "mittel": {"low": 10.0, "mid": 11.5, "high": 13.5}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.5}},
            "ab_2010":   {"einfach": {"low": 10.0, "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.0}, "gut": {"low": 13.0, "mid": 15.5, "high": 18.5}},
        },
    },
    "aachen": {
        "_display": "Aachen", "_year": "2023",
        "_url": "https://www.aachen.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.0}, "gut": {"low": 10.5, "mid": 12.0, "high": 14.0}},
            "1949_1969": {"einfach": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "mittel": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "gut": {"low": 10.0, "mid": 11.5, "high": 13.5}},
            "1970_1990": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.0}, "gut": {"low": 10.5, "mid": 12.0, "high": 14.0}},
            "1991_2009": {"einfach": {"low": 8.5,  "mid": 10.0, "high": 11.5}, "mittel": {"low": 10.0, "mid": 11.5, "high": 13.5}, "gut": {"low": 11.5, "mid": 13.5, "high": 16.0}},
            "ab_2010":   {"einfach": {"low": 10.0, "mid": 11.5, "high": 13.5}, "mittel": {"low": 11.5, "mid": 13.5, "high": 16.0}, "gut": {"low": 13.5, "mid": 16.0, "high": 19.0}},
        },
    },
    "wuppertal": {
        "_display": "Wuppertal", "_year": "2023",
        "_url": "https://www.wuppertal.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1949_1969": {"einfach": {"low": 5.0,  "mid": 6.5,  "high": 8.0},  "mittel": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "gut": {"low": 8.0,  "mid": 9.5,  "high": 11.0}},
            "1970_1990": {"einfach": {"low": 5.5,  "mid": 7.0,  "high": 8.5},  "mittel": {"low": 7.0,  "mid": 8.5,  "high": 10.0}, "gut": {"low": 8.5,  "mid": 10.0, "high": 11.5}},
            "1991_2009": {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "ab_2010":   {"einfach": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "mittel": {"low": 9.5,  "mid": 11.0, "high": 13.0}, "gut": {"low": 11.0, "mid": 13.0, "high": 15.0}},
        },
    },
    "bielefeld": {
        "_display": "Bielefeld", "_year": "2023",
        "_url": "https://www.bielefeld.de/mietspiegel",
        "mietpreisbremse": {"applies": True, "cap_multiplier": 1.10, "neubau_exempt_from": 2014},
        "table": {
            "vor_1949":  {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1949_1969": {"einfach": {"low": 6.0,  "mid": 7.5,  "high": 9.0},  "mittel": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "gut": {"low": 9.0,  "mid": 10.5, "high": 12.5}},
            "1970_1990": {"einfach": {"low": 6.5,  "mid": 8.0,  "high": 9.5},  "mittel": {"low": 8.0,  "mid": 9.5,  "high": 11.0}, "gut": {"low": 9.5,  "mid": 11.0, "high": 13.0}},
            "1991_2009": {"einfach": {"low": 7.5,  "mid": 9.0,  "high": 10.5}, "mittel": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "gut": {"low": 10.5, "mid": 12.5, "high": 14.5}},
            "ab_2010":   {"einfach": {"low": 9.0,  "mid": 10.5, "high": 12.5}, "mittel": {"low": 10.5, "mid": 12.5, "high": 14.5}, "gut": {"low": 12.5, "mid": 14.5, "high": 17.0}},
        },
    },
}

# Aliases for city name variants (umlaut, abbreviations, alternate spellings)
_CITY_ALIASES: dict[str, str] = {
    "koeln": "köln", "cologne": "köln",
    "frankfurt am main": "frankfurt", "frankfurt a.m.": "frankfurt",
    "ffm": "frankfurt",
    "duesseldorf": "düsseldorf",
    "nuernberg": "nürnberg", "nuremberg": "nürnberg",
    "muenster": "münster",
    "freiburg im breisgau": "freiburg", "freiburg i.br.": "freiburg",
    "halle an der saale": "halle", "halle saale": "halle", "halle (saale)": "halle",
    "hannover": "hannover",
}

# ── Bundesland fallback (for cities not in corpus) ───────────────────────────
# mid values €/m²/month by Bundesland and Baujahr bracket
# Used when specific city data is not available
_BUNDESLAND_FALLBACK: dict[str, dict] = {
    "Bayern": {
        "vor_1949": {"einfach": 8.5, "mittel": 10.5, "gut": 12.5},
        "1949_1969": {"einfach": 8.0, "mittel": 10.0, "gut": 12.0},
        "1970_1990": {"einfach": 8.5, "mittel": 10.5, "gut": 12.5},
        "1991_2009": {"einfach": 9.5, "mittel": 11.5, "gut": 13.5},
        "ab_2010":   {"einfach": 11.5, "mittel": 13.5, "gut": 16.0},
    },
    "Baden-Württemberg": {
        "vor_1949": {"einfach": 8.5, "mittel": 10.5, "gut": 12.5},
        "1949_1969": {"einfach": 8.0, "mittel": 10.0, "gut": 12.0},
        "1970_1990": {"einfach": 8.5, "mittel": 10.5, "gut": 12.5},
        "1991_2009": {"einfach": 9.5, "mittel": 11.5, "gut": 13.5},
        "ab_2010":   {"einfach": 11.5, "mittel": 13.5, "gut": 16.0},
    },
    "Nordrhein-Westfalen": {
        "vor_1949": {"einfach": 7.0, "mittel": 9.0, "gut": 11.0},
        "1949_1969": {"einfach": 6.5, "mittel": 8.5, "gut": 10.5},
        "1970_1990": {"einfach": 7.0, "mittel": 9.0, "gut": 11.0},
        "1991_2009": {"einfach": 8.0, "mittel": 10.0, "gut": 12.0},
        "ab_2010":   {"einfach": 9.5, "mittel": 11.5, "gut": 13.5},
    },
    "Hessen": {
        "vor_1949": {"einfach": 8.0, "mittel": 10.0, "gut": 12.0},
        "1949_1969": {"einfach": 7.5, "mittel": 9.5, "gut": 11.5},
        "1970_1990": {"einfach": 8.0, "mittel": 10.0, "gut": 12.0},
        "1991_2009": {"einfach": 9.0, "mittel": 11.0, "gut": 13.0},
        "ab_2010":   {"einfach": 11.0, "mittel": 13.0, "gut": 15.5},
    },
    "Schleswig-Holstein": {
        "vor_1949": {"einfach": 7.5, "mittel": 9.0, "gut": 10.5},
        "1949_1969": {"einfach": 7.0, "mittel": 8.5, "gut": 10.0},
        "1970_1990": {"einfach": 7.5, "mittel": 9.0, "gut": 10.5},
        "1991_2009": {"einfach": 8.5, "mittel": 10.0, "gut": 11.5},
        "ab_2010":   {"einfach": 10.0, "mittel": 11.5, "gut": 13.5},
    },
    "Niedersachsen": {
        "vor_1949": {"einfach": 7.0, "mittel": 8.5, "gut": 10.0},
        "1949_1969": {"einfach": 6.5, "mittel": 8.0, "gut": 9.5},
        "1970_1990": {"einfach": 7.0, "mittel": 8.5, "gut": 10.0},
        "1991_2009": {"einfach": 8.0, "mittel": 9.5, "gut": 11.0},
        "ab_2010":   {"einfach": 9.5, "mittel": 11.0, "gut": 13.0},
    },
    "Rheinland-Pfalz": {
        "vor_1949": {"einfach": 7.0, "mittel": 8.5, "gut": 10.0},
        "1949_1969": {"einfach": 6.5, "mittel": 8.0, "gut": 9.5},
        "1970_1990": {"einfach": 7.0, "mittel": 8.5, "gut": 10.0},
        "1991_2009": {"einfach": 8.0, "mittel": 9.5, "gut": 11.0},
        "ab_2010":   {"einfach": 9.5, "mittel": 11.0, "gut": 13.0},
    },
    "Saarland": {
        "vor_1949": {"einfach": 6.0, "mittel": 7.5, "gut": 9.0},
        "1949_1969": {"einfach": 5.5, "mittel": 7.0, "gut": 8.5},
        "1970_1990": {"einfach": 6.0, "mittel": 7.5, "gut": 9.0},
        "1991_2009": {"einfach": 7.0, "mittel": 8.5, "gut": 10.0},
        "ab_2010":   {"einfach": 8.5, "mittel": 10.0, "gut": 11.5},
    },
    "Brandenburg": {
        "vor_1949": {"einfach": 6.0, "mittel": 7.5, "gut": 9.0},
        "1949_1969": {"einfach": 5.5, "mittel": 7.0, "gut": 8.5},
        "1970_1990": {"einfach": 5.5, "mittel": 7.0, "gut": 8.5},
        "1991_2009": {"einfach": 6.5, "mittel": 8.0, "gut": 9.5},
        "ab_2010":   {"einfach": 8.0, "mittel": 9.5, "gut": 11.5},
    },
    "Sachsen": {
        "vor_1949": {"einfach": 5.5, "mittel": 7.0, "gut": 8.5},
        "1949_1969": {"einfach": 5.0, "mittel": 6.5, "gut": 8.0},
        "1970_1990": {"einfach": 5.0, "mittel": 6.5, "gut": 8.0},
        "1991_2009": {"einfach": 6.0, "mittel": 7.5, "gut": 9.0},
        "ab_2010":   {"einfach": 7.5, "mittel": 9.0, "gut": 10.5},
    },
    "Thüringen": {
        "vor_1949": {"einfach": 5.5, "mittel": 7.0, "gut": 8.5},
        "1949_1969": {"einfach": 5.0, "mittel": 6.5, "gut": 8.0},
        "1970_1990": {"einfach": 5.0, "mittel": 6.5, "gut": 8.0},
        "1991_2009": {"einfach": 6.0, "mittel": 7.5, "gut": 9.0},
        "ab_2010":   {"einfach": 7.5, "mittel": 9.0, "gut": 10.5},
    },
    "Sachsen-Anhalt": {
        "vor_1949": {"einfach": 5.0, "mittel": 6.5, "gut": 8.0},
        "1949_1969": {"einfach": 4.5, "mittel": 6.0, "gut": 7.5},
        "1970_1990": {"einfach": 4.5, "mittel": 6.0, "gut": 7.5},
        "1991_2009": {"einfach": 5.5, "mittel": 7.0, "gut": 8.5},
        "ab_2010":   {"einfach": 7.0, "mittel": 8.5, "gut": 10.0},
    },
    "Mecklenburg-Vorpommern": {
        "vor_1949": {"einfach": 6.0, "mittel": 7.5, "gut": 9.0},
        "1949_1969": {"einfach": 5.5, "mittel": 7.0, "gut": 8.5},
        "1970_1990": {"einfach": 5.5, "mittel": 7.0, "gut": 8.5},
        "1991_2009": {"einfach": 6.5, "mittel": 8.0, "gut": 9.5},
        "ab_2010":   {"einfach": 8.0, "mittel": 9.5, "gut": 11.5},
    },
    "Bremen": {
        "vor_1949": {"einfach": 7.5, "mittel": 9.0, "gut": 10.5},
        "1949_1969": {"einfach": 7.0, "mittel": 8.5, "gut": 10.0},
        "1970_1990": {"einfach": 7.5, "mittel": 9.0, "gut": 10.5},
        "1991_2009": {"einfach": 8.5, "mittel": 10.0, "gut": 11.5},
        "ab_2010":   {"einfach": 10.0, "mittel": 11.5, "gut": 13.5},
    },
    "Hamburg": {
        "vor_1949": {"einfach": 11.0, "mittel": 13.5, "gut": 16.5},
        "1949_1969": {"einfach": 10.0, "mittel": 12.5, "gut": 15.0},
        "1970_1990": {"einfach": 11.0, "mittel": 13.5, "gut": 16.5},
        "1991_2009": {"einfach": 12.5, "mittel": 15.5, "gut": 19.0},
        "ab_2010":   {"einfach": 15.0, "mittel": 18.5, "gut": 22.5},
    },
    "Berlin": {
        "vor_1949": {"einfach": 8.0, "mittel": 10.0, "gut": 12.5},
        "1949_1969": {"einfach": 7.5, "mittel": 9.5, "gut": 11.5},
        "1970_1990": {"einfach": 8.0, "mittel": 10.0, "gut": 12.5},
        "1991_2009": {"einfach": 9.0, "mittel": 11.5, "gut": 14.0},
        "ab_2010":   {"einfach": 11.5, "mittel": 14.5, "gut": 18.0},
    },
}


def _load_json(filename: str) -> dict:
    path = _DATA_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _baujahr_to_simple_key(baujahr: int | None) -> str:
    """Map Baujahr to the 5-bracket key used by inline city data."""
    if baujahr is None:
        return "vor_1949"
    if baujahr < 1949:
        return "vor_1949"
    if baujahr <= 1969:
        return "1949_1969"
    if baujahr <= 1990:
        return "1970_1990"
    if baujahr <= 2009:
        return "1991_2009"
    return "ab_2010"


def _map_baujahr_to_key(baujahr: int | None, city_data: dict) -> str | None:
    """Map Baujahr to the correct table key. Handles both simple and legacy Berlin-style keys."""
    table = city_data.get("table", {})
    keys = list(table.keys())
    if not keys:
        return None

    # If the table uses the simple 5-bracket format, use fast lookup
    if "vor_1949" in table or "1949_1969" in table:
        return _baujahr_to_simple_key(baujahr)

    # Legacy Berlin/Munich/Hamburg key mapping
    if baujahr is None:
        return keys[0]

    mapping = [
        ("vor_1918", None, 1917), ("vor_1919", None, 1918),
        ("1918_1949", 1918, 1949), ("1919_1948", 1919, 1948),
        ("1949_1965", 1949, 1965), ("1950_1964", 1950, 1964),
        ("1965_1972", 1965, 1972), ("1966_1977", 1966, 1977),
        ("1961_1977", 1961, 1977), ("1973_1990", 1973, 1990),
        ("1978_1989", 1978, 1989), ("1978_1990", 1978, 1990),
        ("1991_2002", 1991, 2002), ("1990_1999", 1990, 1999),
        ("2000_2013", 2000, 2013), ("2003_2013", 2003, 2013),
        ("ab_2014", 2014, None),
    ]
    for key, year_from, year_to in mapping:
        if key not in table:
            continue
        low = year_from if year_from else 0
        high = year_to if year_to else 9999
        if low <= baujahr <= high:
            return key
    return keys[-1]


def _infer_wohnlage(stadtteil: str | None, city: str) -> str:
    if stadtteil is None:
        return "mittel"
    st = stadtteil.lower()
    gut_keywords = [
        "mitte", "prenzlauer", "friedrichshain", "charlottenburg", "wilmersdorf",
        "schwabing", "maxvorstadt", "altstadt", "lehel", "bogenhausen",
        "harvestehude", "rotherbaum", "eimsbüttel", "blankenese",
        "westend", "sachsenhausen", "bornheim", "nordend", "innenstadt",
        "altstadt", "stadtmitte", "südstadt", "oststadt",
    ]
    einfach_keywords = [
        "marzahn", "hellersdorf", "spandau", "reinickendorf",
        "neuperlach", "ramersdorf", "hasenbergl",
        "billstedt", "wilhelmsburg", "steilshoop",
        "fechenheim", "zeilsheim", "griesheim",
        "marxloh", "hochfeld", "laar",
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
    bundesland: str | None = None,
) -> RentEstimate:
    """Return Mietspiegel rent estimate for a property.
    Falls back to Bundesland-level estimate if city not in corpus.
    """
    if stadt is None and bundesland is None:
        return RentEstimate(
            miete_kalt_low=0.0, miete_kalt_mid=0.0, miete_kalt_high=0.0,
            per_m2_low=0.0, per_m2_mid=0.0, per_m2_high=0.0,
            city_in_corpus=False,
            notes="Stadt nicht erkannt — manuelle Mieteingabe erforderlich.",
        )

    city_key = (stadt or "").lower().strip()

    # Resolve aliases
    city_key = _CITY_ALIASES.get(city_key, city_key)

    wohnlage = wohnlage_override or _infer_wohnlage(stadtteil, city_key)

    # ── Try JSON-backed cities (Berlin, Munich, Hamburg) ─────────────────────
    if city_key in _JSON_CITY_MAP:
        filename, city_display, year = _JSON_CITY_MAP[city_key]
        city_data = _load_json(filename)
        return _estimate_from_data(
            city_data, city_display, year, baujahr, wohnflaeche_m2, wohnlage, city_in_corpus=True
        )

    # ── Try inline city data ──────────────────────────────────────────────────
    if city_key in _INLINE_CITIES:
        city_data = _INLINE_CITIES[city_key]
        city_display = city_data["_display"]
        year = city_data["_year"]
        return _estimate_from_data(
            city_data, city_display, year, baujahr, wohnflaeche_m2, wohnlage, city_in_corpus=True
        )

    # ── Bundesland fallback ───────────────────────────────────────────────────
    if bundesland and bundesland in _BUNDESLAND_FALLBACK:
        bl_data = _BUNDESLAND_FALLBACK[bundesland]
        bracket = _baujahr_to_simple_key(baujahr)
        row = bl_data.get(bracket, bl_data.get("vor_1949", {}))
        mid_m2 = row.get(wohnlage, row.get("mittel", 9.0))
        low_m2 = mid_m2 * 0.85
        high_m2 = mid_m2 * 1.15
        source = Source(
            name=f"Regionaler Richtwert {bundesland}",
            url="", date="2024",
            confidence=0.55,
            raw_value=f"Bundesland-Schätzwert {bundesland}, {bracket}: €{mid_m2:.1f}/m²",
        )
        return RentEstimate(
            miete_kalt_low=round(low_m2 * wohnflaeche_m2, 0),
            miete_kalt_mid=round(mid_m2 * wohnflaeche_m2, 0),
            miete_kalt_high=round(high_m2 * wohnflaeche_m2, 0),
            per_m2_low=round(low_m2, 2),
            per_m2_mid=round(mid_m2, 2),
            per_m2_high=round(high_m2, 2),
            city_in_corpus=False,
            source=source,
            notes=(
                f"'{stadt}' nicht im Mietspiegel-Korpus. "
                f"Regionaler Schätzwert für {bundesland} verwendet (Konfidenz: mittel). "
                "Manuelle Mieteingabe für genaue Berechnung empfohlen."
            ),
        )

    # ── Final fallback ────────────────────────────────────────────────────────
    return RentEstimate(
        miete_kalt_low=0.0, miete_kalt_mid=0.0, miete_kalt_high=0.0,
        per_m2_low=0.0, per_m2_mid=0.0, per_m2_high=0.0,
        city_in_corpus=False,
        notes=(
            f"'{stadt}' nicht im Mietspiegel-Korpus und Bundesland unbekannt. "
            "Manuelle Mieteingabe erforderlich."
        ),
    )


def _estimate_from_data(
    city_data: dict,
    city_display: str,
    year: str,
    baujahr: int | None,
    wohnflaeche_m2: float,
    wohnlage: str,
    city_in_corpus: bool,
) -> RentEstimate:
    baujahr_key = _map_baujahr_to_key(baujahr, city_data)
    table = city_data.get("table", {})

    if not baujahr_key or baujahr_key not in table:
        return RentEstimate(
            miete_kalt_low=0.0, miete_kalt_mid=0.0, miete_kalt_high=0.0,
            per_m2_low=0.0, per_m2_mid=0.0, per_m2_high=0.0,
            city_in_corpus=city_in_corpus,
            notes=f"Baujahr {baujahr} konnte nicht zugeordnet werden.",
        )

    row = table[baujahr_key].get(wohnlage) or table[baujahr_key].get("mittel", {"low": 0, "mid": 0, "high": 0})
    low_m2 = row["low"]
    mid_m2 = row["mid"]
    high_m2 = row["high"]

    mpb = city_data.get("mietpreisbremse", {})
    mpb_applies = mpb.get("applies", False)
    neubau_exempt_from = mpb.get("neubau_exempt_from", 2014)
    neubau_exempt = bool(baujahr and baujahr >= neubau_exempt_from)
    if neubau_exempt:
        mpb_applies = False

    mpb_cap = mid_m2 * mpb.get("cap_multiplier", 1.10) if mpb_applies else None

    source = Source(
        name=f"Mietspiegel {city_display} {year}",
        url=city_data.get("_url", ""),
        date=city_data.get("_valid_from", year),
        confidence=0.80,
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
        city_in_corpus=city_in_corpus,
        notes=(
            f"Mietspiegel {city_display} {year}, {baujahr_key.replace('_', ' ')}, "
            f"Wohnlage: {wohnlage}. "
            + ("Mietpreisbremse: max. Vergleichsmiete +10%. " if mpb_applies else "")
            + ("Neubau-Ausnahme: Mietpreisbremse gilt nicht. " if neubau_exempt else "")
        ),
    )
