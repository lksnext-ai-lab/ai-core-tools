# pandas cheatsheet

Additional detail beyond `scripts/analyze_dataset.py`'s quick-start.

## Pivot tables

```python
pivot = df.pivot_table(
    index="region", columns="month", values="revenue", aggfunc="sum", fill_value=0
)
```

Equivalent, more general form via `groupby` + `unstack` when `pivot_table`'s
single-aggregation-function limitation doesn't fit:

```python
pivot = df.groupby(["region", "month"], observed=True)["revenue"].sum().unstack("month", fill_value=0)
```

## Merges / joins

```python
merged = orders.merge(customers, on="customer_id", how="left")
# how: "left" | "right" | "inner" | "outer"

# Merge on differently-named key columns
merged = orders.merge(customers, left_on="cust_id", right_on="customer_id")
```

Always check row-count before/after a merge when the join key isn't
guaranteed unique on one side — an unintended one-to-many merge silently
duplicates rows:

```python
before = len(orders)
merged = orders.merge(customers, on="customer_id", how="left")
assert len(merged) == before, "merge duplicated rows — customer_id is not unique on the right side"
```

## Time series

```python
df["date"] = pd.to_datetime(df["date"])
df = df.set_index("date")

monthly = df["revenue"].resample("ME").sum()        # month-end resampling
rolling = df["revenue"].rolling(window=7).mean()     # 7-period rolling average

df["date"].dt.year, df["date"].dt.month, df["date"].dt.dayofweek  # date parts
```

## Reshaping

```python
long = df.melt(id_vars=["region"], value_vars=["Jan", "Feb", "Mar"], var_name="month", value_name="revenue")
wide = long.pivot(index="region", columns="month", values="revenue")
```

## Applying custom logic

Prefer vectorized operations over `.apply()`/`.iterrows()` wherever possible —
they are dramatically faster and idiomatic pandas:

```python
# Slow: df["margin"] = df.apply(lambda r: r["revenue"] - r["cost"], axis=1)
# Fast:
df["margin"] = df["revenue"] - df["cost"]

# Slow: iterating rows to build a new column
# Fast: vectorized conditional
df["tier"] = np.where(df["revenue"] > 1000, "high", "low")

# For genuinely row-wise logic that can't be vectorized, .apply() is the
# correct escape hatch — just don't reach for it by default.
df["label"] = df.apply(lambda row: f"{row['region']}-{row['month']}", axis=1)
```

## Working with JSON-shaped input

```python
import json

records = json.loads(raw_json_text)   # list[dict]
df = pd.json_normalize(records)        # flattens nested dicts into dotted columns
```

## Exporting results

```python
df.to_csv("summary.csv", index=False)
df.to_excel("summary.xlsx", index=False, sheet_name="Summary")
df.to_dict(orient="records")           # back to list[dict] for JSON output
```

## Common pitfalls

- `df.groupby(...)` on a `Categorical` column with unused categories
  (e.g. filtered data) silently includes empty groups unless
  `observed=True` is passed (pandas >= 2.x default is changing this — always
  pass it explicitly for predictable behavior).
- Chained assignment (`df[df.x > 0]["y"] = 1`) triggers a
  `SettingWithCopyWarning` and may silently not modify `df` — assign via
  `df.loc[df.x > 0, "y"] = 1` instead.
- `df.describe()` silently excludes non-numeric columns by default — pass
  `include="object"` (or `include="all"`) to see categorical/text summaries.
- Mixing `float` and `NaN` in an otherwise-integer column upcasts the whole
  column to `float64` — expected pandas behavior, not a bug, but worth
  calling out when the user is surprised their "integer" column show `1.0`.
