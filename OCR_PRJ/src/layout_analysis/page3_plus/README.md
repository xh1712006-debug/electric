# Pages 3+ production analyser

`Page3PlusLayoutAnalysisService` reconstructs setting-table rows, columns,
groups and candidate records from OCR geometry and the shared table-grid
detector. `DocumentLayoutAnalysisService` is retained as a compatibility alias.
Header pagination uses the shared label-independent detector and is exposed as
`layout.page_reference`; its source row is classified as document metadata.
