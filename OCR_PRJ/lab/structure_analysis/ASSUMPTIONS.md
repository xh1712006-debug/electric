# Assumptions for the heuristic layout-graph baseline

These assumptions were recorded after inspecting the repository, production OCR
services, current detector/recognizer outputs, and the available page images.

1. `src.detection.DocumentTextDetectionService` and
   `src.recognition.VietnameseRecognitionService` are the selected OCR pipeline.
   This experiment imports those services when cached OCR is unavailable; it
   does not copy or modify production implementations.
2. Detector polygons are quadrilaterals in original-page pixel coordinates.
   VietOCR results preserve the same polygon and expose detection and recognition
   confidence independently.
3. OCR block order is not reading order. The baseline reconstructs rows and
   columns from geometry after normalizing coordinates to `[0, 1]`.
4. An explicit `page_number` in OCR data takes precedence. Otherwise the page is
   parsed from `page-001` or `_p1` in the filename. Unknown pages default to 1
   and are reported in output metadata. Page 2 is skipped by default.
5. All 20 images currently in `data/image/` resolve to page 1. The repository
   presently contains no page-3+ sample, so variable later-page layouts cannot
   be validated in this run. The algorithm itself has no page-1 coordinates or
   relay-template positions encoded.
6. Existing cached VietOCR output is available for one page. For other pages the
   runner can reuse cached adaptive-threshold detections and invoke VietOCR, or
   invoke both production services if needed.
7. A parameter-code-like token is detected only with a generic syntactic regex.
   No relay-specific parameter name, code list, row number, or pixel coordinate
   is used.
8. Table likelihood is inferred from repeated row/column alignment and optional
   image-line evidence. It is not a definitive table detector.
9. Reconstructed records are hypotheses. Without labeled ground truth, counts
   and visualizations measure behavior and coverage, not correctness.
