# Text recognition comparison lab

The detector has already chosen the text polygons using the watermark-suppressed
`adaptive_threshold` image. This lab deliberately does **not** recognise from
that binary image: it applies the saved polygons to the untouched original
page, perspective-crops each text region, and sends those sharper crops to a
recognition model.

```powershell
python -m pip install -r lab/recognition/requirements.txt
python lab/recognition/run_recognition.py --limit 1 --max-regions 10 --overwrite
```

The default comparison runs these three recognisers and saves each to its own
directory under `lab/recognition/output/{model}/`:

- `vietocr_vgg_transformer`: Vietnamese-specific VietOCR Transformer.
- `svtr_v2`: PaddleOCR's `ch_SVTRv2_rec` model.
- `parseq`: official PARSeq pretrained baseline. Its published checkpoint uses
  a Latin character set, so it is useful for comparison but is not expected to
  preserve Vietnamese diacritics without Vietnamese fine-tuning.

The default recogniser is `PP-OCRv5_mobile_rec`. Compare the mobile and server
recognisers on a small, representative sample with:

```powershell
python lab/recognition/run_recognition.py --models pp_ocr_v5_mobile_rec pp_ocr_v5_server_rec --limit 5 --overwrite
```

Output is written to `lab/recognition/output/{model}/`. Each result JSON
keeps the original detector polygon and score, recognition text and score, and
the crop filename. `annotated/` contains the untouched original page with green
detection polygons and a Unicode recognition label (`index: text (score)`) for
each region. Crops are saved only for audit and visual comparison; source images
and detector outputs remain unchanged.
