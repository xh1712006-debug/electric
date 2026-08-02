# Production layout analysis

The package is separated by the stable role of each page in a relay-adjustment
form:

```text
src/layout_analysis/
├── page1/       fixed cover/header fields and operational notes
├── page2/       intentionally empty; this page is skipped
├── page3_plus/  relay setting tables from page 3 onward
├── table_grid.py
└── service.py   backward-compatible page-3+ import
```

`table_grid.py` is shared because page 1 and pages 3+ both derive logical cells
from the original ruling lines. Production modules do not import from `lab/`.
`pagination.py` is also shared: it detects `x/y` from value structure, expected
page number and header geometry. Words such as `Trang`, `Page` or `Tờ` are
captured as evidence when present, but no label vocabulary is required.

## Page 1

Pass recognised regions from `src.recognition` to the page-1 service:

```python
from src.layout_analysis import Page1LayoutAnalysisService

result = Page1LayoutAnalysisService().analyse_page(
    image_path,
    recognition_result.as_dict()["regions"],
    document_id="7SJ622_1-page-001",
)
payload = result.as_dict()
```

The payload has a fixed field schema. The regulated seven-row, left/right
topology of the first table owns the canonical cover fields; OCR label wording
does not decide their meaning. Original labels are retained separately under
`source_labels`, including when the corresponding value in `fields` is `null`.
If that table cannot be reconstructed, the analyser records
`layout_strategy.cover_fields = "label_fallback"`. Table 02 remains explicitly
skipped, and every extracted value retains source block and bounding-box
evidence.

## Pages 3+

```python
from src.layout_analysis import Page3PlusLayoutAnalysisService

result = Page3PlusLayoutAnalysisService().analyse_page(
    image_path,
    recognition_result.as_dict()["regions"],
    document_id="7SJ622_1-page-003",
    page_number=3,
)
payload = result.as_dict()
```

`DocumentLayoutAnalysisService` remains an alias for
`Page3PlusLayoutAnalysisService`, so existing callers do not need an immediate
import change. Page-3+ records remain auditable geometry candidates until
ground-truth evaluation is available.
