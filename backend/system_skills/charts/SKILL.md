---
name: charts
display_name: Chart Generation
description: >-
  Generate static chart images (line, bar, pie, scatter, histogram) from
  tabular data using matplotlib, saved as PNG files.
when_to_use: >-
  Use this skill when the user asks for a chart, graph, or plot as an
  image file — e.g. "chart this data", "plot revenue over time", "make a bar
  chart of sales by region", or to illustrate a trend/comparison/distribution
  found during data analysis. Typically follows the data-analysis skill,
  which prepares the pandas DataFrame this skill charts. Do not use this
  skill when the destination is an interactive/live chart in a web page or
  document (a static PNG loses hover/inspection) — only use it when a static
  image file is genuinely what's needed (e.g. embedding into a Word document
  or PowerPoint slide, or as a chat attachment).
allowed-tools: code_interpreter
runtime: python3.11
bootstrap_script_path: scripts/bootstrap.sh
---

# Chart generation (matplotlib)

This skill installs [`matplotlib`](https://matplotlib.org/) for generating
static chart images in the sandbox, saved as PNG files.

## When to reach for this skill

- The user explicitly asks for a chart/graph/plot as an image.
- A chart is the clearest way to present a trend, comparison, or distribution
  found during data analysis (see the `data-analysis` skill for preparing the
  data first).
- The output needs to be a static image file — e.g. to embed in a `.docx`
  (`word` skill) or `.pptx` (`pptx` skill) document, or to attach directly to
  the chat response.

If the destination instead supports **live**/interactive charts (e.g. a
first-party document connector that renders charts from data), prefer handing
over the underlying data rather than a rendered image — a picture of a chart
loses hover, data inspection and per-value detail. Use this skill only when a
static image genuinely is the right output.

## Quick start

`scripts/generate_chart.py` builds a small bar chart from an embedded sample
dataset and saves it as `chart.png`. Adapt the data and chart type
(bar/line/pie/scatter/histogram) to the user's actual request.

```bash
python scripts/generate_chart.py
```

## Core matplotlib patterns

### Bar chart

```python
import matplotlib
matplotlib.use("Agg")          # non-interactive backend — required in a headless sandbox
import matplotlib.pyplot as plt

regions = ["North", "South", "East", "West"]
revenue = [1200, 900, 700, 1000]

fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(regions, revenue, color="#4C72B0")
ax.set_title("Revenue by region")
ax.set_xlabel("Region")
ax.set_ylabel("Revenue ($)")
fig.tight_layout()
fig.savefig("chart.png", dpi=150)
plt.close(fig)
```

### Line chart (trend over time)

```python
months = ["Jan", "Feb", "Mar", "Apr"]
revenue = [3800, 4160, 4196, 4500]

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(months, revenue, marker="o", color="#55A868")
ax.set_title("Revenue trend")
ax.set_ylabel("Revenue ($)")
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig("trend.png", dpi=150)
plt.close(fig)
```

### Pie chart

```python
fig, ax = plt.subplots(figsize=(6, 6))
ax.pie(revenue, labels=regions, autopct="%1.1f%%")
ax.set_title("Revenue share by region")
fig.savefig("share.png", dpi=150)
plt.close(fig)
```

### Directly from a pandas DataFrame

```python
import pandas as pd

df = pd.DataFrame({"region": regions, "revenue": revenue})
ax = df.plot.bar(x="region", y="revenue", legend=False, figsize=(8, 5), color="#4C72B0")
ax.set_title("Revenue by region")
ax.figure.tight_layout()
ax.figure.savefig("chart.png", dpi=150)
```

### Histogram / distribution

```python
import numpy as np

values = np.random.default_rng(0).normal(loc=100, scale=15, size=500)
fig, ax = plt.subplots(figsize=(8, 5))
ax.hist(values, bins=30, color="#4C72B0", edgecolor="white")
ax.set_title("Distribution")
fig.savefig("hist.png", dpi=150)
plt.close(fig)
```

## Important: headless backend

Always set `matplotlib.use("Agg")` (or set `MPLBACKEND=Agg`) before importing
`pyplot` — the sandbox has no display server, and the default interactive
backend will fail or hang trying to open one.

See `references/matplotlib-notes.md` for styling, multi-panel figures, and
common gotchas beyond this quick-start.
