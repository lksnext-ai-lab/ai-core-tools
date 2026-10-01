#!/usr/bin/env python3
"""Extract per-page text (pypdf) and any tables (pdfplumber) from a PDF.

Demonstrates the two-library pattern this skill relies on: pypdf for fast
plain-text extraction and page metadata, pdfplumber for tables and
layout-aware text. Designed to work stand-alone against any PDF path, so it
also doubles as a smoke test that both libraries import and run correctly in
the sandbox once ``scripts/bootstrap.sh`` has installed them.

Usage:
    python scripts/extract_text.py path/to/input.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path


def extract_text_per_page(pdf_path: str) -> list[str]:
    """Return a list of per-page extracted text using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return pages


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
    if len(sys.argv) < 2:
        print("usage: python scripts/extract_text.py <path/to/input.pdf>", file=sys.stderr)
        raise SystemExit(2)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).is_file():
        print(f"not a file: {pdf_path}", file=sys.stderr)
        raise SystemExit(2)

    pages = extract_text_per_page(pdf_path)
    print(f"{len(pages)} page(s) extracted from {pdf_path}")
    for i, text in enumerate(pages, start=1):
        preview = text.strip().replace("\n", " ")[:200]
        print(f"--- page {i} ({len(text)} chars) ---")
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
