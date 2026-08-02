# Page 1 production analyser

`Page1LayoutAnalysisService` converts recognised polygons into OCR blocks,
detects the shared table grid and calls the template-aware extractor.

The extractor provides the fixed 25-field page-1 schema, multiline cell value
collection, alias matching, strict relay/software version ownership and source
bbox evidence. The variable protection-principle table (table 02) is retained
only as grid evidence and is intentionally excluded from semantic extraction.

Multiline field ownership uses the complete detected grid when available. If
the grid is incomplete, it combines strong horizontal ruling lines, the next
labelled row, the estimated label/value boundary and a conservative line-gap
limit. This keeps continuation text in the current logical cell while stopping
before checkbox, signature or following data rows.

## Debug one multi-page PDF

The PDF runner renders every page for review but applies this page-1 analyser
only to the first page:

```powershell
python -m src.layout_analysis.page1 data\pdf\one_form.pdf `
  --output output\page1_pdf_debug\one_form
```

It writes `review_overlay.png`, `table_grid.png`, `table_grid.json`,
`page1_layout.json`, raw OCR/detection/recognition JSON, all rendered pages and
`debug_manifest.json`. Use `--reuse-ocr` to rerun layout and overlays from the
matching `ocr_blocks.json` without loading the OCR models again.

Pagination is label-independent. A complete `x/y` pattern in the right-side
header is preferred and validated against the expected page number. If OCR only
retains `x`, the analyser uses its relationship to the ticket row and any
neighbouring label; `total_pages` remains `null` rather than being guessed.
