from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Literal


class Source(BaseModel):
    name: str
    url: str = ""
    date: str = ""          # ISO date string, e.g. "2023-01"
    confidence: float = 1.0  # 0.0–1.0
    raw_value: str = ""      # verbatim text that the value was extracted from


class ExtractedField(BaseModel):
    """Wrapper that carries confidence + source alongside a value."""
    value: float | int | str | bool | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_text: str = ""   # verbatim snippet from the document


class RawListing(BaseModel):
    raw_text: str
    source_url: str | None = None
    source_type: Literal["pdf", "url", "manual"] = "manual"
    image_urls: list[str] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    ocr_used: bool = False


class ExtractedListing(BaseModel):
    # ── Address ────────────────────────────────────────────────
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    plz: str | None = None
    stadt: str | None = None
    stadtteil: str | None = None
    bundesland: str | None = None      # Required for Grunderwerbsteuer

    # ── Property facts ─────────────────────────────────────────
    wohnflaeche_m2: float | None = None  # Required for cashflow
    zimmer: float | None = None
    baujahr: int | None = None
    baualtersklasse: str | None = None   # derived: "1949–1968"
    etage: int | None = None
    gesamtgeschosse: int | None = None
    grundstueck_m2: float | None = None

    # ── Equipment ──────────────────────────────────────────────
    aufzug: bool | None = None
    balkon: bool | None = None
    keller: bool | None = None
    stellplatz: bool | None = None

    # ── Financials (from listing) ───────────────────────────────
    kaufpreis: float | None = None       # Required for cashflow
    kaufpreis_per_m2: float | None = None
    hausgeld_total: float | None = None  # monthly gross
    hausgeld_ruecklage: float | None = None
    grundsteuer_annual: float | None = None
    ist_miete_kalt: float | None = None  # current rent if rented out

    # ── Energy ─────────────────────────────────────────────────
    energieklasse: str | None = None     # "A+", "A", "B", … "H"
    endenergiebedarf_kwh: float | None = None
    heizungsart: str | None = None       # "Fernwärme", "Gas", "Wärmepumpe", …
    heizung_baujahr: int | None = None

    # ── Condition ──────────────────────────────────────────────
    zustand: str | None = None           # "gepflegt", "renovierungsbedürftig", …
    letztes_renovierungsjahr: int | None = None

    # ── WEG ────────────────────────────────────────────────────
    weg_anzahl_einheiten: int | None = None
    teilungserklarung_vorh: bool | None = None
    verwalter: str | None = None

    # ── Meta ───────────────────────────────────────────────────
    red_flags: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_url: str | None = None
    source_type: Literal["pdf", "url", "manual"] = "manual"
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("energieklasse")
    @classmethod
    def normalise_energy_class(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.upper().strip()

    @property
    def baualtersklasse_derived(self) -> str | None:
        if self.baujahr is None:
            return None
        if self.baujahr < 1919:
            return "vor 1919"
        elif self.baujahr <= 1948:
            return "1919–1948"
        elif self.baujahr <= 1968:
            return "1949–1968"
        elif self.baujahr <= 1978:
            return "1969–1978"
        elif self.baujahr <= 1994:
            return "1979–1994"
        elif self.baujahr <= 2009:
            return "1995–2009"
        else:
            return "ab 2010"

    @property
    def requires_user_input(self) -> list[str]:
        """Fields required for cashflow that are missing."""
        required = {
            "kaufpreis": self.kaufpreis,
            "wohnflaeche_m2": self.wohnflaeche_m2,
            "bundesland": self.bundesland,
        }
        return [k for k, v in required.items() if v is None]

    @property
    def is_ready_for_cashflow(self) -> bool:
        return len(self.requires_user_input) == 0
