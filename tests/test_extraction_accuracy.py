"""
Extraction accuracy evaluation harness.
Measures per-field accuracy of Claude Sonnet 4.6 extraction on labeled exposés.

Usage (requires ANTHROPIC_API_KEY in .env):
    pytest tests/test_extraction_accuracy.py -v --tb=short

Skip in CI if no API key:
    pytest tests/test_extraction_accuracy.py --skip-no-key
"""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "labeled_listings.json"

# Fields to evaluate (critical fields weighted higher)
CRITICAL_FIELDS = [
    "kaufpreis", "wohnflaeche_m2", "bundesland", "plz", "stadt",
    "hausgeld_total", "energieklasse", "baujahr",
]
IMPORTANT_FIELDS = [
    "zimmer", "etage", "stadtteil", "ist_miete_kalt", "hausgeld_ruecklage",
    "endenergiebedarf_kwh", "heizungsart", "heizung_baujahr",
    "aufzug", "balkon", "keller", "stellplatz",
    "grundsteuer_annual", "weg_anzahl_einheiten",
]


def _load_fixtures() -> list[dict]:
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _field_match(extracted_val: Any, expected_val: Any, field: str) -> bool:
    """Check if extracted value matches expected within tolerance."""
    if expected_val is None:
        return True  # Cannot evaluate — skip

    if extracted_val is None:
        return False  # Expected something, got nothing

    # Boolean fields
    if isinstance(expected_val, bool):
        return bool(extracted_val) == expected_val

    # Numeric fields — allow 2% tolerance
    if isinstance(expected_val, (int, float)):
        try:
            ratio = abs(float(extracted_val) - float(expected_val)) / max(abs(float(expected_val)), 1.0)
            return ratio <= 0.02
        except (TypeError, ValueError):
            return False

    # String fields — normalized comparison
    if isinstance(expected_val, str):
        ev = str(extracted_val).strip().lower()
        xv = expected_val.strip().lower()
        # Allow partial match for city names (München vs munich)
        if field in ("stadt", "stadtteil", "heizungsart"):
            return ev in xv or xv in ev
        return ev == xv

    return str(extracted_val) == str(expected_val)


class ExtractionEvaluator:
    def __init__(self):
        self.results: list[dict] = []

    def add_result(self, fixture_id: str, field: str, expected: Any, extracted: Any, match: bool):
        self.results.append({
            "fixture": fixture_id,
            "field": field,
            "expected": expected,
            "extracted": extracted,
            "match": match,
        })

    def accuracy(self, fields: list[str]) -> float:
        relevant = [r for r in self.results if r["field"] in fields and r["expected"] is not None]
        if not relevant:
            return 0.0
        return sum(1 for r in relevant if r["match"]) / len(relevant)

    def print_report(self):
        print("\n=== EXTRACTION ACCURACY REPORT ===")
        print(f"Critical fields:  {self.accuracy(CRITICAL_FIELDS):.1%}")
        print(f"Important fields: {self.accuracy(IMPORTANT_FIELDS):.1%}")

        # Per-field breakdown
        all_fields = CRITICAL_FIELDS + IMPORTANT_FIELDS
        field_stats: dict[str, list[bool]] = {}
        for r in self.results:
            if r["expected"] is not None:
                field_stats.setdefault(r["field"], []).append(r["match"])

        print("\nPer-field accuracy:")
        for field in all_fields:
            if field in field_stats:
                acc = sum(field_stats[field]) / len(field_stats[field])
                ok = "OK" if acc >= 0.8 else "FAIL"
                n = len(field_stats[field])
                print(f"  [{ok}] {field:30} {acc:.0%} ({n} samples)")

        # Failures
        failures = [r for r in self.results if not r["match"] and r["expected"] is not None]
        if failures:
            print(f"\nTop failures ({len(failures)} total):")
            for r in failures[:10]:
                print(f"  {r['fixture']}.{r['field']}: expected={r['expected']!r}, got={r['extracted']!r}")


def requires_api_key():
    """Skip marker if no API key configured."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return pytest.mark.skipif(
        not key,
        reason="ANTHROPIC_API_KEY not set — skipping extraction accuracy tests"
    )


@pytest.mark.asyncio
@requires_api_key()
async def test_extraction_accuracy_smoke():
    """Smoke test: run 3 fixtures through extraction, check critical field accuracy."""
    from src.immo2.agents.agent2_extract import extract_listing
    from src.immo2.models.listing import RawListing

    fixtures = _load_fixtures()[:3]  # Only first 3 for smoke test
    evaluator = ExtractionEvaluator()

    for fixture in fixtures:
        raw = RawListing(raw_text=fixture["raw_text"], source_type="manual")
        listing = await extract_listing(raw)

        expected = fixture["expected"]
        for field in CRITICAL_FIELDS + IMPORTANT_FIELDS:
            if field not in expected:
                continue
            extracted_val = getattr(listing, field, None)
            expected_val = expected[field]
            match = _field_match(extracted_val, expected_val, field)
            evaluator.add_result(fixture["id"], field, expected_val, extracted_val, match)

    evaluator.print_report()

    critical_acc = evaluator.accuracy(CRITICAL_FIELDS)
    assert critical_acc >= 0.80, (
        f"Critical field accuracy {critical_acc:.1%} below 80% target. "
        "Fix extraction prompt or labeled data before launch."
    )


@pytest.mark.asyncio
@requires_api_key()
async def test_extraction_accuracy_full():
    """Full evaluation: all 10 fixtures, all fields. Target: ≥85% critical fields."""
    from src.immo2.agents.agent2_extract import extract_listing
    from src.immo2.models.listing import RawListing

    fixtures = _load_fixtures()
    evaluator = ExtractionEvaluator()

    for fixture in fixtures:
        raw = RawListing(raw_text=fixture["raw_text"], source_type="manual")
        listing = await extract_listing(raw)

        expected = fixture["expected"]
        for field in CRITICAL_FIELDS + IMPORTANT_FIELDS:
            if field not in expected:
                continue
            extracted_val = getattr(listing, field, None)
            expected_val = expected[field]
            match = _field_match(extracted_val, expected_val, field)
            evaluator.add_result(fixture["id"], field, expected_val, extracted_val, match)

    evaluator.print_report()

    critical_acc = evaluator.accuracy(CRITICAL_FIELDS)
    important_acc = evaluator.accuracy(IMPORTANT_FIELDS)

    assert critical_acc >= 0.85, (
        f"Critical field accuracy {critical_acc:.1%} below 85% launch target."
    )
    assert important_acc >= 0.70, (
        f"Important field accuracy {important_acc:.1%} below 70% target."
    )


def test_fixture_labels_valid():
    """Validate that all fixtures have required fields and sensible values (no API needed)."""
    fixtures = _load_fixtures()
    assert len(fixtures) == 10, "Expected 10 labeled fixtures"

    for f in fixtures:
        assert "id" in f
        assert "raw_text" in f and len(f["raw_text"]) > 50
        assert "expected" in f
        exp = f["expected"]

        # All fixtures must have kaufpreis and wohnflaeche_m2
        assert "kaufpreis" in exp and exp["kaufpreis"] > 0, f"Missing kaufpreis in {f['id']}"
        assert "wohnflaeche_m2" in exp and exp["wohnflaeche_m2"] > 0, f"Missing wohnflaeche in {f['id']}"
        assert "bundesland" in exp and exp["bundesland"], f"Missing bundesland in {f['id']}"

        # Sanity checks
        assert exp["kaufpreis"] >= 50000, f"Suspicious kaufpreis in {f['id']}"
        assert 10 <= exp["wohnflaeche_m2"] <= 1000, f"Suspicious wohnflaeche in {f['id']}"


def test_field_match_logic():
    """Unit tests for the field matching function."""
    # Numeric tolerance
    assert _field_match(360000.0, 360000, "kaufpreis")
    assert _field_match(360100.0, 360000, "kaufpreis")  # 0.03% diff
    assert not _field_match(380000.0, 360000, "kaufpreis")  # 5.6% diff

    # String matching
    assert _field_match("berlin", "Berlin", "stadt")
    assert _field_match("münchen", "München", "stadt")
    assert _field_match("Gas", "Gaszentralheizung", "heizungsart")  # partial match

    # Boolean
    assert _field_match(True, True, "aufzug")
    assert not _field_match(False, True, "aufzug")

    # None expected → always True (skip evaluation)
    assert _field_match(None, None, "baujahr")
    assert _field_match("anything", None, "baujahr")
