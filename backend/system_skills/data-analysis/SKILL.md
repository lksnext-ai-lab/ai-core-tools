---
name: data-analysis
display_name: Data Analysis (pandas/numpy)
description: >-
  Load, clean and analyze tabular data (CSV/Excel/JSON-shaped data) with
  pandas and numpy — summary statistics, grouping/aggregation, filtering,
  correlation and missing-data checks.
when_to_use: >-
  Use this skill when the user provides or references tabular data (a CSV,
  spreadsheet, or a list/table of records) and asks for summary statistics,
  aggregations (totals/averages/counts by group), filtering, sorting, trend
  analysis, correlations, or a cleaned/transformed version of the data.
  Use it as the data-preparation step before charting (see the charts skill,
  which expects a pandas DataFrame or equivalent as input) or before writing
  a report about the data (see the word skill). Not for single scalar
  arithmetic the model can compute directly without touching a dataset.
allowed-tools: code_interpreter
runtime: python3.11
bootstrap_script_path: scripts/bootstrap.sh
---

# Data analysis (pandas/numpy)

This skill provides pandas/numpy-based tabular data analysis in the sandbox.
Many sandbox images already ship pandas/numpy pre-installed (they are common
Jupyter-kernel dependencies); the bootstrap script pins specific versions to
guarantee behavior is consistent regardless of what the base image happens to
have, and is a fast no-op re-install if those versions are already present.

## When to reach for this skill

- The user supplies data (CSV text, an uploaded CSV/Excel file, or a table
  pasted in the conversation) and wants summary statistics, aggregation,
  filtering, sorting, or a cleaned/transformed version of it.
- A downstream step (a chart via the `charts` skill, a report via the `word`
  skill) needs data loaded into a `pandas.DataFrame` first.

## Quick start

`scripts/analyze_dataset.py` loads a small CSV-shaped dataset (embedded
inline so the script is self-contained and runnable without any input file),
computes summary statistics, and demonstrates grouping/aggregation. Adapt it
to load the user's actual data (`pd.read_csv(path)`, `pd.read_excel(path)`,
or `pd.DataFrame(records)` for JSON-shaped data) instead of the embedded
sample.

```bash
python scripts/analyze_dataset.py
```

## Core pandas/numpy patterns

### Loading data

```python
import pandas as pd

df = pd.read_csv("data.csv")
df = pd.read_excel("data.xlsx", sheet_name="Sheet1")
df = pd.DataFrame(records)  # records: list[dict] — e.g. parsed JSON
```

### Summary statistics

```python
df.info()                      # dtypes, non-null counts
df.describe()                  # count/mean/std/min/quartiles/max for numeric columns
df.describe(include="object")  # for categorical/text columns
df.isna().sum()                # missing values per column
```

### Filtering and sorting

```python
recent = df[df["date"] >= "2025-01-01"]
top10 = df.sort_values("revenue", ascending=False).head(10)
mask = df["region"].isin(["North", "South"]) & (df["revenue"] > 1000)
subset = df[mask]
```

### Grouping and aggregation

```python
by_region = df.groupby("region")["revenue"].agg(["sum", "mean", "count"])

by_region_month = df.groupby(["region", "month"]).agg(
    total_revenue=("revenue", "sum"),
    avg_order_value=("revenue", "mean"),
    orders=("order_id", "count"),
).reset_index()
```

### Correlation

```python
corr = df.select_dtypes(include="number").corr()  # column-pairwise Pearson correlation
```

### Cleaning

```python
df = df.dropna(subset=["revenue"])                 # drop rows missing key values
df["revenue"] = df["revenue"].fillna(0)             # or fill
df["date"] = pd.to_datetime(df["date"])             # parse dates
df = df.drop_duplicates(subset=["order_id"])
```

### numpy for numeric work outside a DataFrame

```python
import numpy as np

values = df["revenue"].to_numpy()
np.mean(values), np.median(values), np.std(values)
np.percentile(values, [25, 50, 75])
```

See `references/pandas-cheatsheet.md` for pivot tables, merges/joins, and
time-series resampling beyond this quick-start.
