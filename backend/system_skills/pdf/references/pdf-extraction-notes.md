# PDF extraction notes

Additional detail beyond `scripts/extract_text.py`'s quick-start, covering the
cases that most often trip up naive PDF extraction.

## Scanned / image-only PDFs

Neither pypdf nor pdfplumber can extract text from a PDF whose pages are
scanned images (no embedded text layer) — `extract_text()` returns an empty
string. Detect this case and fall back to OCR:

```python
from pypdf import PdfReader

reader = PdfReader("input.pdf")
text = "".join((p.extract_text() or "") for p in reader.pages)
if not text.strip():
    print("No text layer found — this PDF is likely scanned; OCR is required.")
```

If OCR is genuinely needed, that is out of scope for this skill (no OCR
library is installed) — use the platform's OCR agent type (`OCRAgent`) instead
of trying to add Tesseract to this sandbox skill.

## Password-protected PDFs

```python
from pypdf import PdfReader

reader = PdfReader("input.pdf")
if reader.is_encrypted:
    reader.decrypt("")          # try an empty password first (some PDFs use
                                 # encryption only to restrict printing/editing,
                                 # not to require a password to open)
```

If decryption fails, the correct password must come from the user — do not
attempt to brute-force it.

## Extraction quality: pypdf vs pdfplumber

- `page.extract_text()` (pypdf) is fast but can interleave multi-column text
  incorrectly, since it extracts in the order text objects appear in the PDF's
  content stream, not necessarily left-to-right/top-to-bottom reading order.
- `page.extract_text(layout=True)` (pdfplumber) reconstructs text using actual
  glyph coordinates, which is much more reliable for multi-column layouts and
  forms, at the cost of being noticeably slower on large documents.
- For a document with tables interleaved with prose, prefer pdfplumber's
  `extract_tables()` for the tables and `extract_text()` for the surrounding
  prose, rather than trying to parse a table out of pypdf's flattened text.

## Table extraction tuning

`extract_tables()` uses heuristics (looking for ruling lines / consistent gaps
between text). If tables are missed or rows/columns are merged incorrectly,
tune the detection strategy explicitly:

```python
import pdfplumber

with pdfplumber.open("input.pdf") as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables(
        table_settings={
            "vertical_strategy": "lines",      # or "text" for borderless tables
            "horizontal_strategy": "lines",
            "snap_tolerance": 3,
        }
    )
```

## Large PDFs

Process page-by-page rather than materializing every page's text/tables
upfront if the PDF is large (hundreds of pages) — both libraries load lazily
per page, but holding all extracted text in memory at once is unnecessary for
a summarization or search task; stream and discard as you go where possible.

## Extracting embedded images

```python
import os
from pypdf import PdfReader

output_dir = "extracted_images"
os.makedirs(output_dir, exist_ok=True)

reader = PdfReader("input.pdf")
for page in reader.pages:
    for i, image in enumerate(page.images):
        # image.name comes from the PDF's internal object naming, which is
        # attacker-controlled (the source document is untrusted) — it can
        # contain "../" or be an absolute path. Never use it as a raw
        # filesystem path; strip it to a basename and write only inside an
        # explicit, intended output directory.
        safe_name = os.path.basename(image.name) or f"image_{i}.png"
        with open(os.path.join(output_dir, safe_name), "wb") as f:
            f.write(image.data)
```

## Common pitfalls

- `extract_text()` can return `None` for a page with no text — always guard
  with `page.extract_text() or ""` before concatenating.
- pdfplumber holds file handles open until the `with pdfplumber.open(...)`
  block exits — always use the context-manager form, not a bare `.open()`
  without `close()`.
- Page numbers in pypdf/pdfplumber are 0-indexed internally (`reader.pages[0]`
  is page 1) — convert to 1-indexed only when presenting results to the user.
