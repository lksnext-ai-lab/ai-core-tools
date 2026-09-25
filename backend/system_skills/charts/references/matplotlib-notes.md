# matplotlib notes

Additional detail beyond `scripts/generate_chart.py`'s quick-start.

## Headless backend (required)

The sandbox has no display server. Always select the non-interactive `Agg`
backend *before* importing `pyplot`:

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
```

If `pyplot` is imported first (directly or transitively, e.g. via
`pandas.DataFrame.plot`), `matplotlib.use("Agg")` may silently have no effect
because a backend was already selected — set the `MPLBACKEND=Agg` environment
variable instead in that case, or make sure this skill's own import order is
followed consistently.

## Figure/axes API vs pyplot state-machine API

Prefer the explicit `fig, ax = plt.subplots()` object-oriented API (used
throughout this skill) over the implicit `plt.plot(...)` state-machine API —
it composes correctly with multiple figures/subplots in the same script and
avoids "which figure am I drawing on" bugs.

```python
fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(...)
fig.savefig("out.png")
plt.close(fig)   # always close — the sandbox process may render many charts
```

## Multi-panel figures

```python
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
axes[0].bar(regions, revenue)
axes[0].set_title("Revenue")
axes[1].bar(regions, units)
axes[1].set_title("Units")
fig.tight_layout()
fig.savefig("panels.png", dpi=150)
plt.close(fig)
```

## Styling

```python
plt.style.use("seaborn-v0_8-whitegrid")   # a clean, readable built-in style

# Or per-axes:
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_axisbelow(True)
ax.grid(True, alpha=0.3)
```

Use `ax.set_title`, `ax.set_xlabel`, `ax.set_ylabel` on every chart — an
unlabeled axis is rarely acceptable in a chart meant for a report or
presentation.

## Value labels on bars

```python
bars = ax.bar(regions, revenue)
ax.bar_label(bars, fmt="$%.0f", padding=3)
```

## Rotating tick labels (long category names)

```python
ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right")
```

## Saving at the right resolution

`dpi=150` is a good default for embedding in a document/slide;
`dpi=300` for print-quality; the default (`dpi=100`) is adequate only for
quick chat-attachment previews. Always call `fig.tight_layout()` before
saving so labels/titles aren't clipped.

## Color choices

Prefer matplotlib's default `tab10`/`tab20` categorical color cycle, or a
small curated palette (e.g. `"#4C72B0"`, `"#55A868"`, `"#C44E52"`,
`"#8172B2"`), over arbitrary named colors — keep a chart's palette
consistent across a set of related charts in the same report/deck.

## Common pitfalls

- Forgetting `plt.close(fig)` after saving leaks figure objects across many
  chart-generation calls in the same long-lived sandbox process — always
  close.
- `fig.savefig(...)` after `plt.show()` (which is a no-op with the `Agg`
  backend anyway) — don't call `plt.show()` in this skill at all, there is no
  display to show it on.
- Default figure size (6.4x4.8 inches) is often too small for a title +
  labeled axes + legend to fit without overlap — pass an explicit `figsize`.
