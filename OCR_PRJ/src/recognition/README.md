# Production Vietnamese recognition

This package is the selected output of the recognition lab: **VietOCR VGG
Transformer**. It uses detector polygons only as geometry, then perspective-
crops the **original** page for recognition. Therefore watermark suppression
helps detection without reducing text detail sent to VietOCR.

Install the worker dependencies:

```powershell
python -m pip install -r src/recognition/requirements.txt
```

Use it after text detection in the asynchronous OCR worker:

```python
from pathlib import Path
from src.recognition import VietnameseRecognitionService

detector_payload = detection_result.as_dict()["detections"]
result = VietnameseRecognitionService().recognise_page(
    Path("/path/to/original-page.png"),
    detector_payload,
)
payload_for_job = result.as_dict()
```

Persist `payload_for_job` with the OCR job. It records each original detector
polygon, detector score, recognised Vietnamese text, recognition confidence,
recogniser version and elapsed time. The original page is never changed.
