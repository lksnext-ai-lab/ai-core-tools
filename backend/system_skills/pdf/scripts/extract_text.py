#!/usr/bin/env python3
"""Extract per-page text (pypdf) and any tables (pdfplumber) from a PDF.

Demonstrates the pattern this skill relies on: pypdf for fast plain-text
extraction and page metadata, pdfplumber for tables and layout-aware text, and
Tesseract OCR (pytesseract) for pages without a text layer. Designed to work
stand-alone against any PDF path, so it also doubles as a smoke test that the
libraries import and run correctly in the sandbox once ``scripts/bootstrap.sh``
has installed them.

Usage:
    python scripts/extract_text.py path/to/input.pdf [--lang spa+eng] [--no-ocr]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

OCR_DPI = 300


def extract_text_per_page(pdf_path: str) -> list[str]:
    """Return a list of per-page extracted text using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return pages


def ocr_pages(pdf_path: str, page_indexes: list[int], lang: str) -> dict[int, str]:
    """OCR the given 0-based pages with Tesseract; return ``{index: text}``."""
    import pypdfium2 as pdfium
    import pytesseract

    results: dict[int, str] = {}
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        for i in page_indexes:
            image = pdf[i].render(scale=OCR_DPI / 72).to_pil()
            results[i] = pytesseract.image_to_string(image, lang=lang)
    finally:
        pdf.close()
    return results


def extract_tables(pdf_path: str) -> list[tuple[int, list[list[str | None]]]]:
    """Return ``(page_number, table_rows)`` for every table pdfplumber finds."""
    import pdfplumber

    found: list[tuple[int, list[list[str | None]]]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                found.append((i, table))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf_path")
    parser.add_argument("--lang", default="spa+eng", help="Tesseract languages, e.g. eus+spa")
    parser.add_argument("--no-ocr", action="store_true", help="skip OCR of pages without text")
    args = parser.parse_args()

    pdf_path = args.pdf_path
    if not Path(pdf_path).is_file():
        print(f"not a file: {pdf_path}", file=sys.stderr)
        raise SystemExit(2)

    pages = extract_text_per_page(pdf_path)
    empty = [i for i, text in enumerate(pages) if not text.strip()]
    ocr_done: set[int] = set()
    if empty and not args.no_ocr:
        if shutil.which("tesseract") is None:
            print(f"{len(empty)} page(s) have no text layer and tesseract is not installed — "
                  "OCR skipped", file=sys.stderr)
        else:
            for i, text in ocr_pages(pdf_path, empty, args.lang).items():
                pages[i] = text
                ocr_done.add(i)

    print(f"{len(pages)} page(s) extracted from {pdf_path}")
    for i, text in enumerate(pages, start=1):
        preview = text.strip().replace("\n", " ")[:200]
        source = ", OCR" if (i - 1) in ocr_done else ""
        print(f"--- page {i} ({len(text)} chars{source}) ---")
        print(preview + ("..." if len(text.strip()) > 200 else ""))

    tables = extract_tables(pdf_path)
    if tables:
        print(f"\n{len(tables)} table(s) found:")
        for page_no, rows in tables:
            print(f"page {page_no}: {len(rows)} row(s)")
    else:
        print("\nno tables detected")


if __name__ == "__main__":
    main()
