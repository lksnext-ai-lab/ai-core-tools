#!/usr/bin/env python3
"""Load a small CSV-shaped dataset and compute summary statistics with pandas/numpy.

The dataset is embedded inline (as CSV text) so this script is fully
self-contained and runnable without any external input file — a genuine
smoke test that pandas/numpy work correctly in the sandbox once
``scripts/bootstrap.sh`` has installed them. Adapt ``load_dataset()`` to load
the user's actual data (``pd.read_csv(path)``, ``pd.read_excel(path)``, or
``pd.DataFrame(records)``) instead of the embedded sample.

Usage:
    python scripts/analyze_dataset.py
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

_SAMPLE_CSV = """order_id,region,month,revenue,units
1,North,Jan,1200.50,12
2,South,Jan,900.00,9
3,East,Jan,700.25,7
4,West,Jan,1000.00,10
5,North,Feb,1300.00,13
6,South,Feb,1050.00,11
7,East,Feb,720.00,7
8,West,Feb,1090.00,11
9,North,Mar,1250.75,12
10,South,Mar,1150.00,12
11,East,Mar,690.50,7
12,West,Mar,1105.25,11
"""


def load_dataset() -> pd.DataFrame:
    """Load the embedded sample dataset. Replace with pd.read_csv(path) for real data."""
    df = pd.read_csv(io.StringIO(_SAMPLE_CSV))
    df["month"] = pd.Categorical(df["month"], categories=["Jan", "Feb", "Mar"], ordered=True)
    return df


def summarize(df: pd.DataFrame) -> None:
    print(f"{len(df)} rows, {len(df.columns)} columns")
    print("\ndtypes:")
    print(df.dtypes)

    print("\nmissing values per column:")
    print(df.isna().sum())

    print("\nnumeric summary statistics:")
    print(df.describe())

    print("\ntotal revenue and units by region:")
    by_region = df.groupby("region", observed=True).agg(
        total_revenue=("revenue", "sum"),
        avg_order_value=("revenue", "mean"),
        total_units=("units", "sum"),
        orders=("order_id", "count"),
    ).sort_values("total_revenue", ascending=False)
    print(by_region)

    print("\nrevenue trend by month (all regions):")
    by_month = df.groupby("month", observed=True)["revenue"].sum()
    print(by_month)

    revenue = df["revenue"].to_numpy()
    print("\nnumpy percentiles on revenue: p25=%.2f p50=%.2f p75=%.2f" % tuple(
        np.percentile(revenue, [25, 50, 75])
    ))

    numeric = df.select_dtypes(include="number").drop(columns=["order_id"])
    print("\ncorrelation matrix (revenue vs units):")
    print(numeric.corr())


def main() -> None:
    df = load_dataset()
    summarize(df)


if __name__ == "__main__":
    main()
