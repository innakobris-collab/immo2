"""
PDF text and table extraction.
Primary: PyMuPDF (text). Secondary: pdfplumber (tables). Fallback: Tesseract OCR.
"""
from __future__ import annotations
import io
from pathlib import Path
from ..models.listing import RawListing


def extract_from_pdf(
    file_bytes: bytes,
    source_url: str | None = None,
) -> RawListing:
    """Extract raw text from a PDF file.
    Tries PyMuPDF first, then pdfplumber for tables, then Tesseract OCR.
    """
    import fitz  # PyMuPDF

    text_parts: list[str] = []
    ocr_used = False

    doc = fitz.open(stream=file_bytes, filetype="pdf")

    for page in doc:
        page_text = page.get_text("markdown")
        if page_text.strip():
            text_parts.append(page_text)

    raw_text = "\n\n".join(text_parts)

    # If very little text extracted (scanned PDF), try pdfplumber then OCR
    if len(raw_text.strip()) < 200:
        raw_text, ocr_used = _extract_with_pdfplumber_and_ocr(file_bytes)

    # Also extract tables via pdfplumber (for Hausgeld breakdowns, WEG tables)
    table_text = _extract_tables_pdfplumber(file_bytes)
    if table_text:
        raw_text = raw_text + "\n\n--- TABELLEN ---\n" + table_text

    doc.close()

    return RawListing(
        raw_text=raw_text,
        source_url=source_url,
        source_type="pdf",
        ocr_used=ocr_used,
    )


def _extract_tables_pdfplumber(file_bytes: bytes) -> str:
    """Extract tables from PDF using pdfplumber."""
    try:
        import pdfplumber
        tables_text: list[str] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    rows = []
                    for row in table:
                        row_str = " | ".join(str(cell or "").strip() for cell in row)
                        if row_str.strip():
                            rows.append(row_str)
                    if rows:
                        tables_text.append("\n".join(rows))
        return "\n\n".join(tables_text)
    except Exception:
        return ""


def _extract_with_pdfplumber_and_ocr(file_bytes: bytes) -> tuple[str, bool]:
    """Fallback: pdfplumber text extraction, then Tesseract OCR."""
    # Try pdfplumber text first
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
        if len(text.strip()) > 200:
            return text, False
    except Exception:
        pass

    # Tesseract OCR fallback
    try:
        import pytesseract
        import fitz
        from PIL import Image
        import numpy as np

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        ocr_parts: list[str] = []
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)  # 2x resolution for better OCR
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang="deu")
            if text.strip():
                ocr_parts.append(text)
        doc.close()
        return "\n\n".join(ocr_parts), True
    except Exception as e:
        return f"[Extraction failed: {e}]", False


def extract_from_text(text: str) -> RawListing:
    """Wrap plain text (from manual input or copy-paste)."""
    return RawListing(
        raw_text=text,
        source_type="manual",
        ocr_used=False,
    )
