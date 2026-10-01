#!/usr/bin/env python3
"""Build a small but complete .pptx deck with python-pptx.

Demonstrates a title slide plus several title+bullets content slides using
the default template's built-in layouts. Run directly to produce
``output.pptx`` in the current working directory, or import
``build_presentation()`` and adapt the slide content to the user's request.

Usage:
    python scripts/build_deck.py [output_path]
"""
from __future__ import annotations

import sys

from pptx import Presentation
from pptx.util import Inches

# (title, [bullet, ...]) for each content slide.
_CONTENT_SLIDES: list[tuple[str, list[str]]] = [
    (
        "Key findings",
        [
            "Revenue grew 12% quarter-over-quarter",
            "Customer churn decreased from 4.1% to 3.2%",
            "Two new product lines launched ahead of schedule",
        ],
    ),
    (
        "Revenue by region",
        [
            "North: $1.2M (+8%)",
            "South: $0.9M (+15%)",
            "East: $0.7M (+3%)",
            "West: $1.0M (+9%)",
        ],
    ),
    (
        "Next steps",
        [
            "Finalize budget for Q4 initiatives",
            "Expand the East region sales team",
            "Review pricing strategy",
        ],
    ),
]


def build_presentation() -> Presentation:
    """Build and return a sample widescreen ``Presentation``. Adapt the content below."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = "Quarterly Report"
    title_slide.placeholders[1].text = "Prepared by Mattin AI"

    for title, bullets in _CONTENT_SLIDES:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        body = slide.placeholders[1].text_frame
        body.text = bullets[0]
        for bullet in bullets[1:]:
            para = body.add_paragraph()
            para.text = bullet
            para.level = 0

    return prs


def main() -> None:
    output_path = sys.argv[1] if len(sys.argv) > 1 else "output.pptx"
    prs = build_presentation()
    prs.save(output_path)
    print(f"Wrote {output_path}")

    # Round-trip sanity check: re-open and print a short structural summary.
    verify = Presentation(output_path)
    print(f"slides={len(verify.slides)}")


if __name__ == "__main__":
    main()
