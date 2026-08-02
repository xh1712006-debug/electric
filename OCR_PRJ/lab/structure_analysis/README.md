# Heuristic layout-graph baseline

This experiment reconstructs candidate logical structure from OCR text blocks
and bounding boxes without a deep-learning layout model. It is the baseline for
later ML comparisons; it does **not** claim correctness without ground truth.

All implementation is contained in `lab/structure_analysis/`. Generated files
are written only under:

```text
lab/structure_analysis/output/heuristic_layout_graph/
```

## Pipeline

1. Reuse cached VietOCR results when available.
2. Otherwise reuse cached adaptive-threshold PP-OCR detection polygons and run
   the production VietOCR recognizer on crops from the original page. If no
   detection cache exists, call both selected production services.
3. Convert every OCR polygon to a node with pixel and `[0, 1]` coordinates.
4. Recover reading rows from vertical overlap and relative center distance.
5. Build generic graph edges: nearest left/right/above/below, same-row
   adjacency, horizontal/vertical overlap, distance, and left-column alignment.
6. Infer possible semantic roles from generic evidence: code-like syntax,
   punctuation, relative position within a row, typography, and alignment.
7. Start record hypotheses from generic parameter-code-like or colon-label
   anchors. Attach aligned following rows as additional values or wrapped
   continuation text.
8. Estimate table-like regions from repeated column anchors and image-line
   evidence. This supports both bordered tables and aligned borderless columns.

No relay parameter names, fixed Y coordinates, template rows, or exact pixel
positions are encoded.

## Run

The current repository has one cached full VietOCR page. Run the fast baseline
on it with:

```powershell
python lab/structure_analysis/run_experiment.py --images 7SJ622_1-page-001.png
```

Run all available images (missing OCR is generated through the selected
production services):

```powershell
python lab/structure_analysis/run_experiment.py
```

Page 2 is skipped by default. Add `--include-page-2` only when it is needed.

Run the synthetic heuristic tests:

```powershell
python -m unittest discover -s lab/structure_analysis/tests -p "test_*.py"
```

## Output contract

Each processed page directory contains:

- `raw_ocr.json`: OCR text, polygon, confidence, page, and model provenance.
- `normalized_blocks.json`: pixel and normalized node geometry plus inferred
  role and record assignment.
- `graph.json`: nodes, recovered rows, and typed geometric edges.
- `reconstructed_structure.json`: record hypotheses, multi-line values, table
  candidates, and explicit no-ground-truth disclaimer.
- `visualization.png`: source page with role-colored boxes, record IDs, and
  grouping links.

The root `summary.json` reports OCR blocks, record counts, multi-line records,
unassigned blocks, possible tables, timings, skipped pages, and errors.

## Limitations and expected failure cases

- OCR errors propagate into role and grouping decisions.
- Closely spaced parallel columns can be connected incorrectly.
- A wrapped line and a new value may be visually indistinguishable; the baseline
  uses code-like syntax and indentation as weak evidence.
- Large gaps, merged detector boxes, rotated text, stamps, handwriting, and
  watermark remnants can break reading-row recovery.
- Repeated alignment suggests a table but does not prove table semantics.
- Current repository samples all resolve to page 1; page-3+ variability remains
  unvalidated until representative later pages and labeled structure are added.
- Counts in `summary.json` measure heuristic coverage, not extraction accuracy.

See `ASSUMPTIONS.md` for the audit-derived assumptions used by this baseline.
