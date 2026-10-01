#!/usr/bin/env python3
"""Generate a static bar chart from a small sample dataset and save it as a PNG.

The dataset is embedded inline so this script is fully self-contained and
runnable without any external input file — a genuine smoke test that
matplotlib renders and saves correctly in the sandbox once
``scripts/bootstrap.sh`` has installed it. Adapt the data and chart type to
the user's actual request (see SKILL.md for line/pie/histogram variants).

Usage:
    python scripts/generate_chart.py [output_path]
"""
from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")  # headless backend — required, no display server in the sandbox

import matplotlib.pyplot as plt

_REGIONS = ["North", "South", "East", "West"]
_REVENUE = [3751.25, 3100.00, 2110.75, 3195.25]


def build_chart(output_path: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(_REGIONS, _REVENUE, color="#4C72B0")
    ax.set_title("Revenue by region (Q1)")
    ax.set_xlabel("Region")
    ax.set_ylabel("Revenue ($)")
    ax.bar_label(bars, fmt="$%.0f", padding=3)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main() -> None:
    output_path = sys.argv[1] if len(sys.argv) > 1 else "chart.png"
    build_chart(output_path)

    import os

    size = os.path.getsize(output_path)
    print(f"Wrote {output_path} ({size} bytes)")
    assert size > 0, "chart file is empty"


if __name__ == "__main__":
    main()
