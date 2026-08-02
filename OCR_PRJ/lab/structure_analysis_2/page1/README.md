# Page-1 layout analysis lab

This folder contains batch and review runners for the production implementation
in `src/layout_analysis/page1`. It runs production detection and VietOCR, calls
the production table/grid extractor, and writes experiment artifacts for human
review. No layout-analysis implementation used at runtime lives in this lab.

The analyser does not use LayoutLMv3 or fixed pixel crops. The variable
six-column protection-principle table (table 02) is currently retained only as
grid evidence and is explicitly skipped by the semantic extractor.

```powershell
.\lab\structure_analysis_2\.venv\Scripts\python.exe -m lab.structure_analysis_2.page1.run_experiment
```

After the first OCR run, iterate on layout without reloading models:

```powershell
.\lab\structure_analysis_2\.venv\Scripts\python.exe -m lab.structure_analysis_2.page1.run_experiment --ocr-blocks lab\structure_analysis_2\page1\output\ocr_blocks.json
```

Run every canonical page-1 image and write `output/<mã_phiếu>/`:

```powershell
.\lab\structure_analysis_2\.venv\Scripts\python.exe -m lab.structure_analysis_2.page1.run_all
```

Rerun layout for all forms from their existing OCR caches:

```powershell
.\lab\structure_analysis_2\.venv\Scripts\python.exe -m lab.structure_analysis_2.page1.run_all --reuse-ocr
```

Outputs are written under `page1/output/`: `page1_layout.json`,
`ocr_blocks.json`, `review_overlay.png`, and `table_grid.png`. The highlighted annotation image is
review guidance only and is never used as inference input.

`fields` has a fixed schema: every declared page-1 field is present. A value
that cannot be extracted is represented as `null`; required missing values are
also recorded in `warnings`.

Labels may span multiple OCR lines, and aliases include equivalent business
wording such as `Tỷ số/ chỉ danh biến ...` and `Nhà sản xuất`. Embedded
known labels are split into virtual text spans with proportional source bounding
boxes when OCR merges several fields into one line. This includes `Phiên bản`,
so relay/software/serial values stop at the label even when the table grid does
not contain an inner divider. A version value must lie to the right of its own
label, in the same logical row, and before the next label; an empty version is
therefore `null` rather than a reused relay/software value. Field evidence keeps
both the original `source_block_ids` and the precise `source_bboxes` used by the
review overlay.

Multiline values are collected from every eligible block in the same logical
cell/row even when the label block already contains a complete-looking first
line. This preserves continuation text such as the second line of `Kiểu bảo vệ`.
Header ticket and page values are resolved independently so a wide page-number
detection cannot consume the ticket number.
If OCR cannot recover the denominator in `Trang: x/y`, the JSON retains
`invalid_page_reference`; it never invents `y`.
