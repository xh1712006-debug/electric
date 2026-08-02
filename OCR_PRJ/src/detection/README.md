# Production text detection

This package is the production output of the detection lab. It runs the
verified **PP-OCRv5 Mobile detector** after applying the automatic two-stage
Otsu preprocessing that suppresses a pale gray diagonal watermark on
PDF-rendered white pages. It also detects substantial red-ink components,
creates a red-stamp mask, removes only those red pixels from the detector input,
and suppresses detections whose polygons are at least 65% inside that mask.

Install worker dependencies:

```powershell
python -m pip install -r src/detection/requirements.txt
```

Use it from the asynchronous OCR worker:

```python
from pathlib import Path
from src.detection import DocumentTextDetectionService

result = DocumentTextDetectionService().detect_page(Path("/path/to/page.png"))
payload_for_job = result.as_dict()
```

Generate visual review output for selected pages:

```powershell
python -m src.detection.preview_red_stamp data\image\page3\PCS-902_4-page-003.png --output output\detection_red_stamp_preview
```

Persist `payload_for_job` together with the OCR job. It contains polygons,
detection scores, preprocessing thresholds, red-stamp mask metadata and a
run-length encoded stamp mask, count of suppressed stamp detections, detector
version and elapsed time. The original file is never modified. The mask must be
retained for later review; a detection that only partly overlaps a stamp is
deliberately kept for human verification.
`lab/detection/` remains the experiment environment and is not a production
dependency.
