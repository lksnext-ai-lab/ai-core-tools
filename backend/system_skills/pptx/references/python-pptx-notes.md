# python-pptx notes

Additional detail beyond `scripts/build_deck.py`'s quick-start.

## Default template slide layouts

`Presentation()` with no arguments loads python-pptx's bundled default
template. Its layout indices (`prs.slide_layouts[N]`) are:

| Index | Layout name          | Placeholders                        |
|-------|-----------------------|--------------------------------------|
| 0     | Title Slide           | title (0), subtitle (1)              |
| 1     | Title and Content     | title (0), content/body (1)          |
| 2     | Section Header        | title (0), text (1)                  |
| 3     | Two Content           | title (0), content (1), content (2)  |
| 4     | Comparison            | title, two headers, two contents     |
| 5     | Title Only            | title (0) only — good for tables/images |
| 6     | Blank                 | none                                  |
| 7     | Content with Caption  | title, content, text                 |
| 8     | Picture with Caption  | title, picture, text                 |

If a custom (uploaded) template is used instead of the default
(`Presentation("template.pptx")`), these indices/names can differ — inspect
`[layout.name for layout in prs.slide_layouts]` before assuming layout 1 is a
bullet-content layout.

## Placeholder indices

Within a slide, `slide.placeholders` is indexed by the placeholder's `idx`
attribute (not necessarily 0, 1, 2, ... in visual order). For the default
template's layouts, `placeholders[0]` is always the title and `placeholders[1]`
is the body/subtitle — but for a custom template, enumerate them first:

```python
for ph in slide.placeholders:
    print(ph.placeholder_format.idx, ph.placeholder_format.type, ph.name)
```

## Bullet levels and formatting

```python
body = slide.placeholders[1].text_frame
body.text = "Top-level bullet"           # sets paragraph 0's text
p1 = body.add_paragraph()
p1.text = "Second-level bullet"
p1.level = 1                              # 0-4, deeper = more indented

# Per-run formatting (bold/italic/size/color), same pattern as python-docx
run = p1.runs[0]
run.font.bold = True
run.font.size = Pt(18)
```

## Speaker notes

```python
notes_slide = slide.notes_slide          # creates one if it doesn't exist
notes_slide.notes_text_frame.text = "Remember to mention the Q4 roadmap."
```

## Tables

```python
from pptx.util import Inches

table_shape = slide.shapes.add_table(rows, cols, left, top, width, height)
table = table_shape.table
table.cell(0, 0).text = "Header"
table.columns[0].width = Inches(2)
```

## Charts (native PowerPoint charts, not images)

```python
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

chart_data = CategoryChartData()
chart_data.categories = ["North", "South", "East", "West"]
chart_data.add_series("Revenue", (1.2, 0.9, 0.7, 1.0))
slide.shapes.add_chart(
    XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1.5), Inches(8), Inches(4.5), chart_data
)
```

Prefer a native chart (as above) over embedding a matplotlib PNG when the
deck's audience might want to edit the chart's data directly in PowerPoint.
Use the `charts` skill (matplotlib) instead when a static, precisely-styled
image is what's actually wanted, or the visualization type isn't a chart type
PowerPoint natively supports.

## Common pitfalls

- `slide.shapes.title` is `None` on layouts without a title placeholder
  (e.g. layout 6, "Blank") — check before assigning `.text`.
- `text_frame.text = "..."` replaces ALL paragraphs in that frame with a
  single one — use `add_paragraph()` for subsequent bullets, not repeated
  `.text` assignment.
- This library only supports the modern `.pptx` (Office Open XML) format —
  legacy binary `.ppt` files are not supported and must be converted first
  (e.g. via LibreOffice headless conversion) outside this skill.
- Slide dimensions default to 10x7.5in (4:3) unless explicitly set to
  13.333x7.5in (16:9) as shown in `scripts/build_deck.py`.
