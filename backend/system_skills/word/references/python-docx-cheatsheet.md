# python-docx cheatsheet

Reference notes for working with `.docx` files beyond `scripts/create_document.py`'s
quick-start. All of this assumes `from docx import Document` and `python-docx`
installed by `scripts/bootstrap.sh`.

## Document structure basics

A `Document` is a flat sequence of block-level items (paragraphs and tables) at
the body level, plus sections that control page layout. Headings are just
paragraphs with a `"Heading N"` style applied.

```python
doc = Document()                 # new, blank document
doc = Document("existing.docx")  # open an existing file
```

## Headings and paragraph styles

```python
doc.add_heading("Title", level=0)     # "Title" style
doc.add_heading("Chapter 1", level=1) # "Heading 1"
doc.add_heading("Section 1.1", level=2)

doc.add_paragraph("Plain body text")
doc.add_paragraph("Quoted text", style="Intense Quote")
doc.add_paragraph("Bullet item", style="List Bullet")
doc.add_paragraph("Numbered item", style="List Number")
```

Available built-in styles depend on the template but the ones above ship with
python-docx's default template and are safe to use unconditionally.

## Runs (inline formatting)

A paragraph's text is made of one or more `Run` objects; formatting (bold,
italic, underline, font, size, color) is set per-run, not per-paragraph.

```python
from docx.shared import Pt, RGBColor

p = doc.add_paragraph()
run = p.add_run("Important: ")
run.bold = True
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
p.add_run("read this carefully.")
```

## Tables

```python
table = doc.add_table(rows=2, cols=3)
table.style = "Light Grid Accent 1"   # any built-in table style name
table.cell(0, 0).text = "Header"
row = table.add_row()                 # add rows dynamically
row.cells[0].text = "Value"

# Merge cells
a = table.cell(0, 0)
b = table.cell(0, 1)
a.merge(b)
```

Useful built-in table styles: `"Table Grid"` (plain grid), `"Light List Accent 1"`,
`"Light Grid Accent 1"`, `"Medium Shading 1 Accent 1"`.

## Page layout / sections

```python
from docx.shared import Inches
from docx.enum.section import WD_ORIENT

section = doc.sections[0]
section.left_margin = Inches(1)
section.right_margin = Inches(1)
section.orientation = WD_ORIENT.LANDSCAPE
section.page_width, section.page_height = section.page_height, section.page_width
```

## Page breaks

```python
doc.add_page_break()
```

## Images

```python
from docx.shared import Inches
doc.add_picture("chart.png", width=Inches(5))
```

## Headers and footers

```python
section = doc.sections[0]
header = section.header
header.paragraphs[0].text = "Confidential — internal use only"
footer = section.footer
footer.paragraphs[0].text = "Page footer text"
```

## Reading content back out

```python
doc = Document("input.docx")

# Paragraphs in document order, with their style name
for para in doc.paragraphs:
    if para.text.strip():
        print(f"[{para.style.name}] {para.text}")

# Tables: iterate rows -> cells
for t_idx, table in enumerate(doc.tables):
    for row in table.rows:
        print(t_idx, [cell.text for cell in row.cells])
```

To preserve *reading order* across mixed paragraphs and tables (python-docx's
`.paragraphs`/`.tables` are separate flat lists and lose interleaving), walk the
underlying XML body directly:

```python
from docx.table import Table
from docx.text.paragraph import Paragraph

def iter_block_items(doc):
    for child in doc.element.body.iterchildren():
        if child.tag.endswith('}p'):
            yield Paragraph(child, doc)
        elif child.tag.endswith('}tbl'):
            yield Table(child, doc)

for block in iter_block_items(doc):
    if isinstance(block, Paragraph):
        print("P:", block.text)
    else:
        print("T:", [c.text for r in block.rows for c in r.cells])
```

## Common pitfalls

- `doc.add_heading(..., level=0)` uses the `"Title"` style, not `"Heading 0"` —
  there is no heading level 0 style by that name.
- Table cell text assignment (`cell.text = "..."`) replaces the cell's entire
  content with a single run — any existing per-run formatting in that cell is
  lost. Access `cell.paragraphs[0].add_run(...)` instead if you need to append
  formatted text into an existing cell.
- `.docx` is a zip archive of XML parts; never hand-edit it as text. Always go
  through python-docx (or another dedicated library) for structural changes.
- This skill only handles `.docx` (Office Open XML). Legacy binary `.doc` files
  are a different format and are not supported by python-docx.
