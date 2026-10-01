#!/usr/bin/env python3
"""Create a small but complete .docx document with python-docx.

Demonstrates the building blocks an agent needs for most Word-generation
requests: a title, section headings, body paragraphs with inline formatting,
a bulleted list and a real (not ASCII-art) table. Run directly to produce
``output.docx`` in the current working directory, or import
``build_document()`` and adapt it to the user's actual content.

Usage:
    python scripts/create_document.py [output_path]
"""
from __future__ import annotations

import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH


def build_document() -> Document:
    """Build and return a sample report ``Document``. Adapt the content below."""
    doc = Document()

    doc.add_heading("Quarterly Report", level=0)

    subtitle = doc.add_paragraph("Prepared by Mattin AI")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].italic = True

    doc.add_heading("Summary", level=1)
    p = doc.add_paragraph("This report covers ")
    p.add_run("Q3 2025").bold = True
    p.add_run(
        " performance across all regions, highlighting revenue growth, key "
        "risks, and recommended next steps."
    )

    doc.add_heading("Key findings", level=1)
    for bullet in (
        "Revenue grew 12% quarter-over-quarter, driven by the South region.",
        "Customer churn decreased from 4.1% to 3.2%.",
        "Two new product lines launched ahead of schedule.",
    ):
        doc.add_paragraph(bullet, style="List Bullet")

    doc.add_heading("Revenue by region", level=1)
    headers = ["Region", "Revenue", "Growth"]
    rows = [
        ("North", "$1.2M", "+8%"),
        ("South", "$0.9M", "+15%"),
        ("East", "$0.7M", "+3%"),
        ("West", "$1.0M", "+9%"),
    ]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    hdr_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        hdr_cells[i].text = header
        for run in hdr_cells[i].paragraphs[0].runs:
            run.bold = True
    for region, revenue, growth in rows:
        cells = table.add_row().cells
        cells[0].text, cells[1].text, cells[2].text = region, revenue, growth

    doc.add_heading("Next steps", level=1)
    for i, step in enumerate(
        ("Finalize budget for Q4 initiatives", "Expand the East region sales team", "Review pricing strategy"),
        start=1,
    ):
        doc.add_paragraph(f"{step}", style="List Number")

    return doc


def main() -> None:
    output_path = sys.argv[1] if len(sys.argv) > 1 else "output.docx"
    doc = build_document()
    doc.save(output_path)
    print(f"Wrote {output_path}")

    # Round-trip sanity check: re-open and print a short structural summary.
    verify = Document(output_path)
    print(f"paragraphs={len(verify.paragraphs)} tables={len(verify.tables)}")


if __name__ == "__main__":
    main()
