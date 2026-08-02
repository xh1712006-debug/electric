# Hướng dẫn candidate scoring Page 1

Tài liệu này dành cho **IMMEDIATE-001B**. Scoring engine hiện độc lập với
extractor production; việc nối candidate thật của Page 1 vào engine thuộc các
task IMMEDIATE-001C–001E.

## Quy tắc hiện tại

Mỗi candidate cung cấp sáu signal từ `0.0` đến `1.0`: `topology`, `anchor`,
`alias`, `separator`, `value_validation` và `ocr_confidence`. Engine nhân signal
với weight trong `src/layout_analysis/page1/field_rules.json` và lưu từng phép
tính trong `breakdown`.

Năm confidence levels là:

| Level | Label | Khoảng effective score |
| --- | --- | --- |
| 1 | `very_low` | 0 đến dưới 20 |
| 2 | `low` | 20 đến dưới 40 |
| 3 | `medium` | 40 đến dưới 60 |
| 4 | `high` | 60 đến dưới 80 |
| 5 | `very_high` | 80 đến 100 |

Thiếu dấu `:` có signal `separator=0` và không sinh điểm âm. Dấu `:` hợp lệ có
thể dùng `separator=1` để nhận đủ bonus. Hard value validator fail phải tạo
`HardConstraint.value_validation_failure()`: effective score bị cap dưới 40,
confidence tối đa level 2 và candidate không được auto-select.

Winner chỉ được auto-select khi đạt `auto_select_minimum`, hơn runner-up ít nhất
`winner_margin_minimum`, và không có hard constraint. Với đúng một candidate,
margin không áp dụng; threshold và hard constraints vẫn áp dụng.

## Sửa weights hoặc thresholds

Cách an toàn là tạo overlay riêng, không sửa rule built-in. Ví dụ:

```json
{
  "schema_version": "1.0",
  "scoring": {
    "auto_select_minimum": 75,
    "winner_margin_minimum": 18,
    "weights": {
      "topology": 25,
      "anchor": 25,
      "alias": 15,
      "separator": 10,
      "value_validation": 20,
      "ocr_confidence": 5
    }
  },
  "fields": {}
}
```

Weights phải có đủ sáu key, mỗi giá trị trong khoảng 0–100 và tổng bằng 100.
Loader sẽ từ chối overlay sai thay vì âm thầm dùng cấu hình một phần.

## Chạy test tự động

Chạy riêng scoring engine:

```powershell
python -m unittest tests.test_page1_scoring -v
```

Chạy registry và scoring cùng nhau:

```powershell
python -m unittest tests.test_page1_field_rules tests.test_page1_scoring -v
```

Chạy toàn bộ verification chuẩn của repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Nếu `python` trên PATH không dùng được nhưng venv lab hiện có vẫn hoạt động, có
thể chạy focused test và visual report ngay bằng:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_page1_scoring -v

& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.layout_analysis.page1.scoring_visual `
  --output .\output\page1_scoring\scoring_review.html
```

Để sửa dứt điểm root `.venv` cho các E2E model/UI sau này, chạy bootstrap rồi
thay `python` trong các lệnh bằng `& ".\.venv\Scripts\python.exe"`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_debug_ui.ps1 -RecreateVenv
```

## Chạy kiểm thử trực quan

Sinh báo cáo HTML mẫu, không cần OCR model hoặc dependency giao diện:

```powershell
python -m src.layout_analysis.page1.scoring_visual `
  --output .\output\page1_scoring\scoring_review.html
```

Mở `output/page1_scoring/scoring_review.html` bằng trình duyệt. Báo cáo hiển thị
winner, trạng thái auto-select/review, margin, raw/effective score, confidence,
hard caps và thanh điểm cho từng component.

Có thể truyền fixture UTF-8 riêng bằng `--input` và overlay bằng `--overlay`:

```powershell
python -m src.layout_analysis.page1.scoring_visual `
  --input .\my_scoring_fixture.json `
  --overlay .\field_rules.user.json `
  --output .\output\page1_scoring\custom_review.html
```

Fixture có dạng:

```json
{
  "candidates": [
    {
      "candidate_id": "candidate-a",
      "canonical_field": "relay_version",
      "value": "V6.7.0.2",
      "component_scores": {
        "topology": 1.0,
        "anchor": 1.0,
        "alias": 1.0,
        "separator": 1.0,
        "value_validation": 1.0,
        "ocr_confidence": 0.95
      },
      "hard_constraints": []
    }
  ]
}
```

Để mô phỏng hard validator fail, thêm:

```json
"hard_constraints": [
  {"reason": "unit_suffix_mismatch", "max_confidence_level": 2}
]
```

---

# Hướng dẫn topology và anchor resolver Page 1

Phần này bổ sung cho **IMMEDIATE-001C** và không thay thế hướng dẫn scoring ở
trên. Resolver hiện độc lập với extractor production; việc nối evidence vào
output Page 1 thuộc IMMEDIATE-001E.

## Quy ước hình học

`SpatialCandidate` nhận bbox `(x1, y1, x2, y2)`, kích thước trang, value và
optional `source_cell`. Mọi khoảng cách được chia cho chiều cao chữ trung bình
của candidate/anchor, vì vậy cùng một layout cho kết quả giống nhau ở nhiều DPI.

Các relation hỗ trợ: `above`, `below`, `left`, `right`, `same_row`,
`same_column` và `same_row_right`. Mặc định:

- sai lệch cùng hàng tối đa `0.75` text height;
- sai lệch cùng cột tối đa `2.0` text heights;
- khoảng cách direction tối đa `8.0` text heights;
- khoảng cách same-axis tối đa `12.0` text heights;
- overlap theo trục vuông góc tối thiểu `0.20`.

Có thể đổi các giá trị này khi khởi tạo mà không sửa thuật toán:

```python
from src.layout_analysis.page1 import (
    RelationshipPolicy,
    TopologyAnchorResolver,
    load_field_rule_registry,
)

resolver = TopologyAnchorResolver(
    load_field_rule_registry(),
    RelationshipPolicy(
        same_row_tolerance=0.8,
        same_column_tolerance=2.0,
        direction_max_distance=9.0,
        same_axis_max_distance=12.0,
        minimum_orthogonal_overlap=0.2,
    ),
)
```

Chỉ nên đổi tolerance sau khi có fixture/ground truth tương ứng. Không đưa pixel
threshold tuyệt đối vào policy. `source_cell` có dữ liệu và sai `cover_row/slot`
sẽ tạo hard constraint level 2; thiếu `source_cell` là `not_evaluated`, không bị
coi nhầm là mismatch.

## Chạy test tự động

```powershell
python -m unittest tests.test_page1_relationships -v

python -m unittest `
  tests.test_page1_relationships `
  tests.test_page1_scoring `
  tests.test_page1_layout_analysis -v

powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Fallback hiện dùng được trên máy này:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_page1_relationships -v
```

## Chạy test trực quan topology/anchor

Sinh báo cáo HTML/SVG mặc định:

```powershell
python -m src.layout_analysis.page1.relationship_visual `
  --output .\output\page1_relationships\relationship_review.html
```

Báo cáo gồm ticket/page-reference hai chiều, relay-name/version cùng hàng bên
phải và một candidate sai Table-01 cell bị tô đỏ/hard-cap. Mở file
`output/page1_relationships/relationship_review.html` bằng trình duyệt.

Để chạy fixture riêng:

```powershell
python -m src.layout_analysis.page1.relationship_visual `
  --input .\my_relationship_fixture.json `
  --overlay .\field_rules.user.json `
  --output .\output\page1_relationships\custom_review.html
```

Fixture UTF-8 có dạng:

```json
{
  "cases": [
    {
      "title": "Relay version",
      "canonical_field": "relay_version",
      "candidate": {
        "candidate_id": "version",
        "bbox": [880, 420, 1010, 450],
        "page_width": 1200,
        "page_height": 1600,
        "value": "V6.7.0.2",
        "source_cell": "table_01:cover_row_1:right_secondary"
      },
      "anchors": {
        "relay_name": [
          {
            "candidate_id": "relay",
            "bbox": [620, 420, 770, 450],
            "page_width": 1200,
            "page_height": 1600,
            "value": "SEL311L",
            "source_cell": "table_01:cover_row_1:right_primary"
          }
        ]
      }
    }
  ]
}
```

---

# Hướng dẫn alias, dấu hai chấm và value validators Page 1

Phần này bổ sung cho **IMMEDIATE-001D**; nội dung scoring và topology/anchor ở
trên vẫn được giữ nguyên. Resolver mới chưa nối vào extractor production cho
đến IMMEDIATE-001E.

## Quy tắc alias và separator

`AliasSeparatorResolver` đọc toàn bộ active aliases trong registry, so khớp
không phân biệt hoa/thường và dấu tiếng Việt, nhưng giữ nguyên OCR text và
provenance trong evidence. Alias dài/cụ thể nhất thắng tại cùng vị trí; nếu cùng
một alias thuộc nhiều canonical fields thì tất cả fields đều được trả về để
scoring quyết định sau.

Alias rất ngắn như `Số` chỉ hợp lệ khi có `:`/`：`, đứng cuối block hoặc theo sau
bởi code/value. Vì vậy `Số:` không nhầm với `Số hiệu`, `Số trang`, `Số lượng`.
Dấu hai chấm hợp lệ tạo `separator_score=1`; thiếu dấu không tạo điểm âm.

Có thể truyền các OCR block logic liền nhau để ghép label/value:

```python
from src.layout_analysis.page1 import AliasSeparatorResolver, load_field_rule_registry

resolver = AliasSeparatorResolver(load_field_rule_registry())
candidates = resolver.resolve_blocks([
    "Mục đích ban hành",
    "phiếu",
    "Nâng cấp trạm",
])
```

Chỉ ghép các block đã được geometry xác định là lân cận/cùng ownership; không
đưa toàn bộ trang vào một lần vì có thể trộn các hàng độc lập.

## Cấu hình value rules

Các type hỗ trợ: `unit_suffix`, `endswith`, `startswith`, `regex`, `enum`,
`numeric`, `numeric_range`, `version`, `ticket_number`; đồng thời giữ hỗ trợ
`year` và `page_reference` đang có trong registry mặc định.

Ví dụ overlay append-only:

```json
{
  "schema_version": "1.0",
  "fields": {
    "current_transformer_ratio": {
      "value_rules": [
        {
          "type": "unit_suffix",
          "values": ["A"],
          "required": true,
          "origin": "user",
          "created_by": "operator-a"
        }
      ]
    }
  }
}
```

`unit_suffix` bỏ whitespace nên `20A` và `20 A` tương đương. `regex` dùng
full-match. `enum` so khớp normalized exact. `numeric` nhận dấu thập phân `.`
hoặc `,`. `numeric_range` dùng `minimum`/`maximum` với hai biên inclusive.
Required rule fail tạo hard-cap confidence level 2; optional rule fail chỉ làm
giảm `value_validation` score.

## Chạy test tự động

```powershell
python -m unittest tests.test_page1_value_resolution -v

python -m unittest `
  tests.test_page1_value_resolution `
  tests.test_page1_field_rules `
  tests.test_page1_scoring `
  tests.test_page1_relationships `
  tests.test_page1_layout_analysis -v

powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Fallback hiện dùng được trên máy này:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_page1_value_resolution -v
```

## Chạy test trực quan bằng tiếng Việt

```powershell
python -m src.layout_analysis.page1.value_resolution_visual `
  --output .\output\page1_value_resolution\value_resolution_review.html
```

Báo cáo hiển thị bằng tiếng Việt có dấu: OCR đầu vào, alias khớp, giá trị tách
ra, dấu hai chấm, kết quả validator, normalized value và hard-cap mức 2.

Chạy fixture/overlay riêng:

```powershell
python -m src.layout_analysis.page1.value_resolution_visual `
  --input .\my_value_resolution_fixture.json `
  --overlay .\field_rules.user.json `
  --output .\output\page1_value_resolution\custom_review.html
```

Fixture UTF-8 có dạng:

```json
{
  "alias_cases": [
    {
      "title": "Label và value tách block",
      "blocks": ["Mục đích ban hành phiếu", "Nâng cấp trạm"]
    }
  ],
  "validation_cases": [
    {
      "title": "Kiểm tra đơn vị Ampe",
      "field": "demo_current",
      "value": "20 A",
      "rules": [
        {
          "type": "unit_suffix",
          "values": ["A"],
          "required": true,
          "origin": "user"
        }
      ]
    }
  ]
}
```

---

# Hướng dẫn tích hợp field resolution vào Page 1

Phần này bổ sung cho **IMMEDIATE-001E** và được nối tiếp sau các hướng dẫn
scoring, topology/anchor và value validators. Production output vẫn giữ
`schema_version: "1.1"`, toàn bộ canonical names và cấu trúc cũ trong `fields`.
Evidence mới chỉ được thêm ở top-level `field_resolution`.

## Quy tắc an toàn khi phân giải field

- Field đã có giá trị không bị registry/scoring ghi đè.
- Table 01 tiếp tục do topology cố định sở hữu. Slot có label nhưng không có
  value vẫn là `null`; alias bên ngoài bảng không được điền vào slot đó.
- Khi không dựng được Table 01, cover field đang `null` chỉ được bổ sung nếu có
  cover-slot topology khớp hoặc anchor rule khớp; alias + score đơn thuần không
  đủ quyền sở hữu field.
- Registry alias chỉ bổ sung một field đang `null` khi decision là
  `auto_selected`, đạt ngưỡng điểm/margin và không có hard constraint.
- Candidate `review_required`, hai candidate không đủ margin hoặc validator bắt
  buộc fail chỉ tạo evidence, không thay đổi `fields`.
- Component không áp dụng vì field không có rule tương ứng được coi là neutral
  trong integration layer. Rule có cấu hình nhưng thiếu/sai evidence vẫn nhận
  điểm 0 hoặc hard-cap theo đúng resolver/validator.

Mỗi field có evidence gồm `resolution_method`, `matched_rule`, `anchor`,
`topology`, `value_validation`, `score_breakdown`, `confidence`,
`winner_margin` và `decision`. Ví dụ đọc evidence:

```python
result = service.analyse_page(
    image_path,
    recognised_regions,
    document_id="P_001",
).as_dict()

ticket = result["fields"]["ticket_number"]
ticket_resolution = result["field_resolution"]["ticket_number"]
print(ticket["text"])
print(ticket_resolution["confidence"])
print(ticket_resolution["decision"]["reasons"])
```

## Nạp overlay khi chạy production service

Không sửa trực tiếp `field_rules.json` cho alias riêng. Tạo overlay append-only
rồi truyền vào service:

```python
from src.layout_analysis.page1 import Page1LayoutAnalysisService

service = Page1LayoutAnalysisService(
    field_rule_overlay_path="field_rules.user.json",
)
```

Không truyền đồng thời `field_rule_overlay_path` và `field_rule_registry`.
Overlay sai schema, provenance hoặc rule type bị từ chối ngay khi khởi tạo.

## Chạy test tự động

Focused integration và backward compatibility:

```powershell
python -m unittest tests.test_page1_field_resolution_integration -v
```

Regression Page 1 và debug UI:

```powershell
python -m unittest `
  tests.test_page1_field_resolution_integration `
  tests.test_page1_layout_analysis `
  tests.test_page1_field_rules `
  tests.test_page1_scoring `
  tests.test_page1_relationships `
  tests.test_page1_value_resolution `
  tests.test_page1_pdf_debug `
  tests.test_debug_ui -v
```

Full repository verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Fallback Python hiện dùng được trên máy này:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_page1_field_resolution_integration -v
```

## Chạy test trực quan bằng tiếng Việt

Sinh báo cáo demo 25 field, gồm auto-select, review-required, score breakdown,
confidence, winner margin và hard-cap mức 2:

```powershell
python -m src.layout_analysis.page1.field_resolution_visual `
  --output .\output\page1_field_resolution\field_resolution_review.html
```

Render một `page1_layout.json` đã có `field_resolution`:

```powershell
python -m src.layout_analysis.page1.field_resolution_visual `
  --input .\output\page1_pdf_debug\P_003\page1_layout.json `
  --output .\output\page1_field_resolution\P_003_review.html
```

## Audit before/after trên OCR thật đã cache

Lệnh sau đọc 19 ảnh Page 1 và OCR cache thật, chạy production extractor mới,
so sánh toàn bộ canonical field names và mọi field đã có giá trị. Null-to-value
được ghi riêng là supplement; non-null value bị đổi được coi là regression và
CLI trả exit code 1.

```powershell
python -m src.layout_analysis.page1.field_resolution_audit `
  --image-root .\data\image\page1 `
  --cache-root .\lab\structure_analysis_2\page1\output `
  --output .\output\page1_field_resolution\real_data_audit.json
```

Artifact mặc định:

- `output/page1_field_resolution/field_resolution_review.html`
- `output/page1_field_resolution/real_data_audit.json`

Cache thật hiện có `Số:` và `Mục đích ban hành phiếu` trên 19 tài liệu,
`Phiên bản rơ-le` trên một tài liệu. Chưa có OCR thật chứa
`Nguyên nhân thay đổi chỉnh định`; biến thể này được khóa bằng integration
fixture UTF-8 và phải tiếp tục để `review_required` nếu không đủ evidence.

---

# Hướng dẫn contract local API v1 cho một PDF_x

Phần này bổ sung cho **IMMEDIATE-001** và được nối tiếp sau các hướng dẫn Page
1. Contract hiện là tài liệu/fixture đã chốt để các task sau triển khai; chưa có
`RelayFormOcrService.process_pdf` chạy thật cho đến IMMEDIATE-002–004.

## Các file contract

- `docs/LOCAL_API_CONTRACT_V1.md`: quyết định request/result/error, lifecycle,
  artifact boundary và backward compatibility.
- `contracts/local_api/v1/contract_manifest.json`: catalog machine-readable cho
  required fields, enums, error codes và policy.
- `contracts/local_api/v1/examples/*.json`: bốn acceptance fixtures UTF-8 gồm
  thành công, thành công có cảnh báo, cần review và thất bại.
- `scripts/local_api_contract_review.py`: validator và HTML renderer không cần
  dependency ngoài Python standard library.

## Quy tắc sửa đổi

1. Không thêm production orchestration hoặc Pydantic model vào contract task;
   implementation tương ứng thuộc IMMEDIATE-002 và IMMEDIATE-003.
2. Khi thêm optional field không phá consumer cũ, cập nhật manifest, tài liệu,
   đủ bốn fixtures và tests. Khi xóa/đổi tên field, đổi type/nullability, đổi
   enum semantics hoặc path base, phải tăng major `schema_version`.
3. `request` được chứa absolute `input_pdf`/`output_root`; `result` không được
   chứa absolute path. Artifact chỉ dùng `relative_path` dưới `output_root`.
4. Không đưa `raw_ocr`, detection/recognition payload, image path, Streamlit
   state, traceback hoặc stack trace vào public result.
5. Page 3+ setting records và note candidates luôn giữ
   `review_status=review_required` cho đến khi có quality gate nghiệp vụ.
6. Successful Page 1 examples phải giữ đủ 25 canonical field keys, kể cả field
   có `value: null`.
7. Không sửa file HTML sinh ra để thay đổi contract. Sửa manifest/fixtures hoặc
   renderer, chạy test, rồi sinh lại HTML.

## Chạy contract tests

Focused contract, boundary, single-file, UTF-8 và visual tests:

```powershell
python -m unittest tests.test_local_api_contract -v
```

Fallback Python đang hoạt động trên máy này:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_local_api_contract -v
```

Full repository verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

## Sinh test trực quan bằng tiếng Việt

Kiểm tra bốn fixtures rồi sinh báo cáo HTML. Command trả exit code 1 và không
sinh báo cáo mới nếu fixture vi phạm contract:

```powershell
python -m scripts.local_api_contract_review `
  --output .\output\local_api_contract\contract_review.html
```

Dùng một contract root khác để thử migration hoặc thay đổi chưa commit:

```powershell
python -m scripts.local_api_contract_review `
  --contract-root .\contracts\local_api\v1 `
  --output .\output\local_api_contract\contract_review_custom.html
```

Báo cáo hiển thị bằng tiếng Việt có dấu: processing status, review status, số
Page 1 fields có giá trị, số setting candidates, warnings, public error,
artifact paths và kết quả contract validation. Artifact mặc định:

- `output/local_api_contract/contract_review.html`

## Giới hạn hiện tại

Validator của IMMEDIATE-001 kiểm tra contract fixtures và security boundary,
không tuyên bố runtime đã conform. IMMEDIATE-002 tạo document orchestrator,
IMMEDIATE-003 tạo typed schema/JSON Schema, còn IMMEDIATE-004 mới cung cấp
public Python API chạy thật. CLI JSON vẫn là adapter bắt buộc ở IMMEDIATE-005.

---

# Document orchestrator production cho một PDF_x

Phần này bổ sung cho **IMMEDIATE-002**. Orchestration xử lý một PDF_x đã được chuyển
khỏi Debug UI sang `src/relay_form_ocr`; Debug UI chỉ còn quản lý upload, tách PDF_A,
session và hiển thị kết quả.

## Thành phần và ranh giới sửa đổi

- `src/relay_form_ocr/orchestrator.py`: implementation production duy nhất cho render,
  routing Page 1/Page 2/Page 3+, detection, recognition, layout, aggregation, warning và
  artifact manifest.
- `src/relay_form_ocr/visual.py`: sinh báo cáo HTML độc lập bằng tiếng Việt có dấu.
- `src/debug_ui/pipeline.py`: adapter mỏng gọi orchestrator; không đặt thêm business
  routing hoặc aggregation tại đây.
- Page 2 tiếp tục có trạng thái `skipped_by_document_policy`; không gọi detection,
  recognition hoặc layout cho trang này.
- Page 3+ và note vẫn là candidate cần người dùng xem xét. Không tự động xác nhận dữ
  liệu nghiệp vụ khi chưa có ground truth/quality gate.
- `important_field_resolution` tổng hợp evidence và năm mức confidence từ Page 1.
  Không sửa trực tiếp evidence trong orchestrator; thay đổi scoring/validator phải thực
  hiện tại `src/layout_analysis/page1`.
- Artifact trong `artifacts` phải dùng đường dẫn tương đối với thư mục output. Typed
  public schema và `RelayFormOcrService.process_pdf` thuộc IMMEDIATE-003/004, không nên
  được chèn sớm vào adapter Debug UI.

## Chạy test tập trung và toàn bộ

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_document_orchestrator tests.test_debug_ui -v
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Test tập trung bao phủ routing, Page 2 policy, model load/reuse, aggregation,
warning propagation, renderer/layout thật với OCR giả, architecture boundary,
Debug UI delegation và HTML UTF-8.

## Sinh test trực quan tiếng Việt

Sinh báo cáo từ fixture mẫu có đủ ba vai trò trang và năm mức confidence:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.visual `
  --output .\output\document_orchestrator\orchestrator_review.html
```

Sinh lại báo cáo từ kết quả OCR thật:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.visual `
  --input .\output\document_orchestrator\P_003\extraction.json `
  --output .\output\document_orchestrator\P_003\orchestrator_review.html
```

Mở file HTML bằng trình duyệt để xem tổng quan trang, routing, cảnh báo được truyền,
năm mức độ tin cậy, trường Page 1 và artifact tương đối.

## Chạy E2E nội bộ với P_003.pdf

Đây là evidence runner dành cho phát triển, chưa phải public CLI của IMMEDIATE-005.
Không truyền callback in tiếng Việt nếu console Windows chưa được cấu hình UTF-8.

```powershell
@'
import json
from pathlib import Path
from src.pdf_form_splitter.pdf_io import pdf_page_count
from src.relay_form_ocr import DocumentOcrOrchestrator, PdfCandidate

source = Path("data/pdf_split/documents/P_003.pdf").resolve()
candidate = PdfCandidate(
    "e2e-p003", source.name, str(source), pdf_page_count(source), "repository_fixture"
)
result = DocumentOcrOrchestrator(use_gpu=False, render_dpi=160).extract_pdf_x(
    candidate, Path("output/document_orchestrator/P_003")
)
print(json.dumps(result["summary"], ensure_ascii=True))
'@ | & ".\lab\structure_analysis_2\.venv\Scripts\python.exe" -
```

Kết quả đầy đủ nằm tại `output/document_orchestrator/P_003/extraction.json`; từng trang
nằm trong `pages/`, ảnh render nằm trong `rendered/`. Lần chạy CPU đầu tiên có thể mất
vài phút vì phải khởi tạo VietOCR và PaddleOCR.

---

# Typed request/result/error schema v1

Phần này bổ sung cho **IMMEDIATE-003**. Public contract được triển khai bằng Pydantic
v2, tách biệt với dict nội bộ của document orchestrator. `RelayFormOcrService` sẽ nối
orchestrator với các model này trong IMMEDIATE-004.

## Public models và file schema

- `src/relay_form_ocr/schemas.py`: `OcrRequest`, `OcrResult` và toàn bộ nested models.
- `contracts/local_api/v1/schemas/ocr_request.schema.json`: JSON Schema request v1.
- `contracts/local_api/v1/schemas/ocr_result.schema.json`: JSON Schema result v1.
- `src/relay_form_ocr/schema_export.py`: exporter deterministic cho hai schema.
- `src/relay_form_ocr/schema_visual.py`: validator fixture và HTML review tiếng Việt.
- `src/relay_form_ocr/requirements.txt`: dependency `pydantic>=2.10,<3`.

Caller có thể import trực tiếp:

```python
from src.relay_form_ocr import OcrRequest, OcrResult, PublicError
```

Mọi nested model đều từ chối field lạ và là immutable. `OcrResult` kiểm tra invariant
giữa processing status, review status, warning, business, error, page coverage và
artifact references. Đủ 25 canonical Page 1 fields được khai báo thành thuộc tính rõ
ràng; không dùng `Any` cho business, page, warning, artifact hoặc error envelope.

## Quy tắc sửa đổi

1. Sửa model trong `schemas.py`, không sửa trực tiếp JSON Schema đã sinh.
2. Giữ `extra="forbid"`; field mới phải là optional nếu muốn tương thích schema v1.
3. Xóa/đổi tên field, đổi type/nullability, thay enum semantics hoặc artifact path base
   là breaking change và phải tăng major `schema_version`.
4. Confidence level phải khớp label: 1/rất thấp, 2/thấp, 3/trung bình, 4/cao,
   5/rất cao; score nằm trong 0–100.
5. Page 3+ setting records và note candidates luôn dùng `review_required`.
6. Public result không chứa raw OCR, image/temp/input/output absolute path, model object,
   traceback hoặc stack trace. Chi tiết lỗi theo từng exception sẽ được khử dữ liệu nhạy
   cảm thêm trong IMMEDIATE-007.
7. Artifact path dùng dấu `/`, là relative path dưới output root, không chứa `..`;
   checksum/workspace runtime được hoàn thiện ở IMMEDIATE-006.
8. Sau mỗi thay đổi model, export lại schema, chạy focused tests và kiểm tra diff schema
   trước khi commit.

## Export lại JSON Schema

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.schema_export `
  --output-dir .\contracts\local_api\v1\schemas
```

Test sẽ fail nếu schema đã commit không còn khớp typed model hoặc exporter không sinh
kết quả deterministic.

## Chạy test typed contract

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_local_api_models tests.test_local_api_contract -v
```

Kiểm tra dependency và toàn repository:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" -m pip check
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Test bao phủ required/extra fields, path types, enum/nullability/numeric bounds,
confidence consistency, bốn fixtures v1, UTF-8 round-trip, cross-field invariants,
review safety, traversal, absolute path, traceback/debug payload, artifact references,
JSON Schema determinism và backward compatibility.

## Sinh test trực quan tiếng Việt

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.schema_visual `
  --fixture-dir .\contracts\local_api\v1\examples `
  --output .\output\local_api_schema\schema_review.html
```

Báo cáo hiển thị số fixture hợp lệ, bốn tình huống success/warning/review/failure,
danh mục typed models, 25 Page 1 fields, năm mức confidence và các biên an toàn.
Artifact mặc định:

- `output/local_api_schema/schema_review.html`

Trình duyệt tự động trong ứng dụng có thể chặn URL `file://`; renderer, nội dung tiếng
Việt UTF-8 và cả bốn scenario vẫn được kiểm tra tự động. Có thể mở file HTML trực tiếp
bằng trình duyệt desktop để review giao diện.

---

# Synchronous local Python API

Phần này bổ sung cho **IMMEDIATE-004**. Public service nhận đúng một `OcrRequest`, gọi
document orchestrator production và luôn trả một terminal `OcrResult` cho các lỗi
runtime dự kiến. Service không dùng Streamlit, debug UI hoặc working directory cố định.

## Cách gọi public API

```python
from pathlib import Path
from src.relay_form_ocr import OcrRequest, RelayFormOcrService

service = RelayFormOcrService()
request = OcrRequest(
    input_pdf=Path(r"D:\management-data\P_001.pdf"),
    output_root=Path(r"D:\ocr-artifacts"),
    correlation_id="ticket-123",
)
result = service.process_pdf(request)
payload = result.model_dump(mode="json")
```

`RelayFormOcrService` giữ cùng một `DocumentOcrOrchestrator` trong suốt vòng đời
instance, vì vậy VietOCR được load trước PaddleOCR và cả hai model được tái sử dụng
giữa các call tuần tự. Tạo một service dùng lâu dài thay vì tạo service mới cho từng PDF.

Lưu ý: constructor public hiện nhận `orchestrator`, `page_counter` và
`pipeline_version` cho composition/test; GPU/render tuning được cấu hình bằng một
`DocumentOcrOrchestrator` truyền vào:

```python
from src.relay_form_ocr import DocumentOcrOrchestrator, RelayFormOcrService

service = RelayFormOcrService(
    orchestrator=DocumentOcrOrchestrator(use_gpu=False, render_dpi=160)
)
```

## Workspace và lỗi runtime

- Workspace hiện tại là `output_root/<correlation_id>/`.
- Service không ghi đè workspace đã có dữ liệu. Dùng correlation ID mới cho lần chạy
  mới; collision/isolation policy nâng cao thuộc IMMEDIATE-006.
- `OcrRequest` sai type hoặc sai schema bị Pydantic/typed boundary từ chối.
- Sau khi request hợp lệ, file không tồn tại, directory, chữ ký/cấu trúc PDF sai,
  output không ghi được và pipeline exception đều trở thành `OcrResult(status="failed")`.
- Failure result không chứa raw exception, stack trace hoặc absolute internal path.
- Page 3+ setting records và `Lưu ý` luôn là candidate `review_required`; Page 2 tiếp
  tục `skipped_by_policy` kèm warning.
- Artifacts public có checksum, byte size và đường dẫn tương đối dưới `output_root`;
  raw OCR/debug layout chỉ nằm trong artifact, không nhúng vào typed business result.

## Quy tắc sửa đổi service

1. Sửa public composition/mapping trong `src/relay_form_ocr/service.py`; không tạo
   pipeline OCR thứ hai.
2. Giữ orchestration render/detect/recognise/layout tại `orchestrator.py`.
3. Nếu thay public payload, sửa `schemas.py`, export lại JSON Schema và chạy contract
   tests trước khi sửa mapper.
4. Không trả dict nội bộ, `image_path`, `raw_ocr`, model object hoặc exception text cho
   caller.
5. Giữ model lifecycle theo một service instance. Error mapping chi tiết theo từng
   stage, progress callback và structured logging thuộc IMMEDIATE-007.
6. Chính sách workspace/checksum/collision/security đầy đủ thuộc IMMEDIATE-006; thay
   đổi path base là breaking contract change.

## Chạy test public API

Focused API, integration, external-cwd, failure và visual tests:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_local_api_service -v
```

Chạy cùng typed contract và orchestrator regressions:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest `
  tests.test_local_api_service `
  tests.test_local_api_models `
  tests.test_local_api_contract `
  tests.test_document_orchestrator -v
```

Toàn repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

## Sinh test trực quan tiếng Việt

Sinh lại HTML từ typed result đã có mà không chạy OCR:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.service_visual `
  --result-json .\output\local_python_api\public_result.json `
  --output .\output\local_python_api\service_review.html
```

Chạy E2E public service với PDF thật, lưu typed JSON và sinh HTML:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.service_visual `
  --input-pdf .\data\pdf_split\documents\P_003.pdf `
  --output-root .\output\local_python_api `
  --correlation-id immediate-004-p003-run-002 `
  --output .\output\local_python_api\service_review_run_002.html
```

Harness chỉ in ASCII trên console để tương thích Windows `cp1258`; file JSON và HTML
vẫn là UTF-8, hiển thị tiếng Việt có dấu. Báo cáo gồm trạng thái xử lý/review, Page 1,
Page 2 policy, Page 3+, warnings, artifacts, timing, lỗi public và đủ năm mức confidence.
Nếu in-app browser chặn `file://`, chạy web server chỉ đọc trong một terminal:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m http.server 8765 `
  --bind 127.0.0.1 `
  --directory .\output\local_python_api
```

Sau đó mở `http://127.0.0.1:8765/service_review.html`; nhấn `Ctrl+C` trong terminal
để dừng server. Browser QA ngày 2026-07-30 xác nhận report thật của `P_003.pdf` render
đúng ở viewport 1265×720, không tràn ngang và không có warning/error trong console.

# Local CLI JSON adapter

Phần này bổ sung cho **IMMEDIATE-005** và gọi trực tiếp public
`RelayFormOcrService`; không có pipeline OCR thứ hai. Dùng adapter khi hệ thống quản lý
không chạy Python hoặc muốn tích hợp qua subprocess trên cùng server.

## Gọi CLI và đọc JSON từ stdout

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$raw = & ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr `
  --input ".\data\pdf_split\documents\P_003.pdf" `
  --output-root ".\output\local_cli_json" `
  --correlation-id "management-ticket-123" `
  --json
$exitCode = $LASTEXITCODE
$result = $raw | ConvertFrom-Json
```

`--json` là cờ tương thích với contract ban đầu; output của adapter luôn là JSON.
CLI tự resolve các đường dẫn tương đối trước khi tạo typed `OcrRequest`. Khi gọi qua
Windows PowerShell, đặt `OutputEncoding` thành UTF-8 như trên để giữ nguyên tiếng Việt
có dấu.

Muốn ghi JSON thẳng vào file thay vì stdout:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr `
  --input ".\data\pdf_split\documents\P_003.pdf" `
  --output-root ".\output\local_cli_json" `
  --correlation-id "management-ticket-124" `
  --json `
  --output-json ".\output\local_cli_json\public_result_124.json"
```

Khi dùng `--output-json`, stdout rỗng. CLI mặc định từ chối ghi đè file kết quả đã có.
Chỉ thêm `--overwrite-result` khi caller chủ động muốn thay file; replacement được ghi
qua file tạm rồi thay nguyên tử. Không dùng cùng đường dẫn cho `--input` và
`--output-json`.

## stdout, stderr và exit code

- stdout chỉ chứa đúng một machine JSON khi không dùng `--output-json`.
- stderr chứa log bắt đầu/kết thúc và output từ thư viện OCR/model. Không parse stderr
  thành business result.
- Service failure sau khi request hợp lệ vẫn là đầy đủ `OcrResult` v1.
- Lỗi parser/request trước service dùng CLI-error JSON có `cli_schema_version=1.0`.
- `--help` là human-readable help, không phải machine invocation.

| Exit code | Cách xử lý phía consumer |
|---:|---|
| `0` | Parse `OcrResult`; vẫn kiểm tra `status`, `review_status` và warnings. |
| `2` | Sửa command/options/request; không retry nguyên lệnh sai. |
| `3` | Kiểm tra đường dẫn, file và cấu trúc PDF_x. |
| `4` | Kiểm tra quyền ghi, workspace collision hoặc result file đã tồn tại. |
| `5` | OCR/render/layout thất bại; đọc public error để quyết định retry/review. |
| `70` | Lỗi adapter; giữ stderr cho chẩn đoán và chuyển human review. |

## Quy tắc sửa đổi CLI

1. Sửa parser, stream isolation và exit mapping tại
   `src/relay_form_ocr/cli.py`; giữ `__main__.py` chỉ làm entry point mỏng.
2. Không gọi trực tiếp orchestrator từ CLI. Mọi request phải đi qua
   `RelayFormOcrService.process_pdf(OcrRequest)`.
3. Không in progress, model warning hoặc log bằng `print()` ra machine stdout.
4. Nếu đổi option, error envelope hoặc exit-code semantics, cập nhật đồng thời
   `docs/LOCAL_API_CONTRACT_V1.md`, test subprocess và consumer documentation.
5. Không đưa exception text, traceback hoặc absolute input/output path vào JSON lỗi
   của adapter.
6. Workspace/artifact hardening nâng cao thuộc IMMEDIATE-006; structured progress và
   granular log/error mapping thuộc IMMEDIATE-007.

## Chạy test CLI

Focused parser, failure, subprocess, stream và PowerShell platform tests:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_local_api_cli -v
```

Chạy cùng public API/schema/contract/orchestrator regressions:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest `
  tests.test_local_api_cli `
  tests.test_local_api_service `
  tests.test_local_api_models `
  tests.test_local_api_contract `
  tests.test_document_orchestrator -v
```

Toàn repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

## Sinh và mở test trực quan tiếng Việt

Sinh report từ typed JSON đã có mà không chạy lại OCR:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.cli_visual `
  --result-json ".\output\local_cli_json\public_result.json" `
  --output ".\output\local_cli_json\cli_review.html"
```

Report mô tả luồng Parse → Validate → Process → Emit, tách stdout/stderr, đủ bảng exit
code và kết quả OCR thật; toàn bộ nhãn giải thích dùng tiếng Việt có dấu. Mở qua local
server chỉ đọc nếu browser chặn `file://`:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m http.server 8766 `
  --bind 127.0.0.1 `
  --directory ".\output\local_cli_json"
```

Sau đó mở `http://127.0.0.1:8766/cli_review.html` và nhấn `Ctrl+C` để dừng server.
Browser QA ngày 2026-07-30 xác nhận report E2E render đúng ở viewport 1265 px, có 4
thẻ tổng quan, 6 dòng exit code, một panel stdout, một panel stderr, không tràn ngang
và console không có warning/error.

# Workspace và artifact isolation

Phần này bổ sung cho **IMMEDIATE-006**. Mỗi lời gọi public API/CLI giữ độc quyền
workspace xác định:

```text
<output_root>/
└── <correlation_id>/
    ├── .relay_form_ocr_workspace.json
    ├── artifact_manifest.json
    ├── rendered/
    ├── pages/
    └── extraction.json
```

Nếu `<output_root>/<correlation_id>` đã tồn tại, kể cả là thư mục rỗng, lời gọi mới
thất bại với collision và không ghi đè. Vì vậy caller phải cấp correlation ID mới cho
mỗi lần chạy. Runtime từ chối `..`, absolute artifact path, dấu `\` trong relative
artifact path, tên Windows dành riêng, symlink và Windows reparse point tại output
root/workspace/artifact.

`artifact_manifest.json` được ghi UTF-8 bằng atomic replace khi pipeline thành công
hoặc thất bại. Manifest chứa source SHA-256 trước/sau, `source_unchanged`, marker state
và size/checksum của từng artifact vật lý. Manifest là một public artifact trong
`OcrResult`, nhưng không tự liệt kê trong danh sách entries của chính nó.

## Quy tắc sửa đổi

1. Sửa reservation, path/reparse guard, checksum, marker, finalize hoặc cleanup tại
   `src/relay_form_ocr/workspace.py`.
2. Sửa cách public service tạo/finalize workspace hoặc map lỗi an toàn tại
   `src/relay_form_ocr/service.py`; không tạo một workspace policy riêng trong CLI.
3. Giữ `artifact_manifest.json` là manifest vật lý UTF-8, atomic và không self-reference.
   Thay tên, path base hoặc semantics của manifest là thay đổi contract và phải cập nhật
   model, fixture, `docs/LOCAL_API_CONTRACT_V1.md` và consumer tests.
4. Không nới path validation bằng cách resolve rồi bỏ qua symlink/reparse. Chỉ kiểm kê
   regular file nằm dưới đúng workspace đã có marker hợp lệ.
5. Source PDF là read-only. Nếu hash sau pipeline khác hash trước pipeline, kết quả phải
   failed an toàn và manifest phải ghi `source_unchanged=false`.
6. Không thêm auto-cleanup, retention hoặc quota ngầm. Cleanup phải tiếp tục dry-run mặc
   định và cần xác nhận tường minh cho đúng correlation ID.

## Chạy test workspace

Focused unit/security/isolation/source/Unicode/cleanup/visual tests:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_workspace_isolation -v
```

Chạy cùng toàn bộ public API regressions liên quan:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest `
  tests.test_workspace_isolation `
  tests.test_local_api_service `
  tests.test_local_api_cli `
  tests.test_local_api_models `
  tests.test_local_api_contract `
  tests.test_document_orchestrator -v
```

Toàn repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

## Audit manifest và source bất biến

Sau một lần chạy, đọc `artifact_manifest.json` trong workspace và kiểm tra:

- `workspace_id` trùng correlation ID;
- `state` là `completed` hoặc `failed`;
- `source.sha256_before` bằng `source.sha256_after` và `source.unchanged=true`;
- mỗi entry tồn tại dưới `output_root`, đúng `size_bytes` và `sha256`;
- danh sách entries không chứa chính `artifact_manifest.json`.

Fixture contract có thể validate trực tiếp tại
`contracts/local_api/v1/workspace_manifest.example.json`; tests sử dụng cùng validator
production để phát hiện schema/path/checksum sai.

## Cleanup thủ công an toàn

Lệnh mặc định chỉ lập kế hoạch, không xóa dữ liệu:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.workspace_cleanup `
  --output-root ".\output\workspace_isolation\kết-quả" `
  --correlation-id "immediate-006-p003"
```

Đọc machine JSON trả về và xác nhận `dry_run=true`, `deleted=false`, đường dẫn và số
file/byte đúng workspace dự kiến. Chỉ khi thực sự muốn xóa mới chạy lại với:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.workspace_cleanup `
  --output-root ".\output\workspace_isolation\kết-quả" `
  --correlation-id "immediate-006-p003" `
  --confirm-delete
```

Cleanup từ chối workspace thiếu/sai marker, correlation ID khác, path escape,
symlink/reparse hoặc file không phải regular file. Không dùng `Remove-Item -Recurse`
thay cho command này trong luồng vận hành production.

## Sinh và mở test trực quan tiếng Việt

Sinh report từ manifest đã có mà không chạy lại OCR:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.workspace_visual `
  --manifest ".\output\workspace_isolation\kết-quả\immediate-006-p003\artifact_manifest.json" `
  --output ".\output\workspace_isolation\workspace_review.html"
```

Report hiển thị workspace ID/state, source trước/sau, bốn bước lifecycle, toàn bộ
artifact ID/type/path/size/checksum và hàng rào an toàn bằng tiếng Việt có dấu. Nếu
browser chặn `file://`, chạy server chỉ đọc:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m http.server 8767 `
  --bind 127.0.0.1 `
  --directory ".\output\workspace_isolation"
```

Sau đó mở `http://127.0.0.1:8767/workspace_review.html` và nhấn `Ctrl+C` để dừng
server. Browser QA ngày 2026-07-30 trên report E2E xác nhận đúng 17 dòng artifact,
bốn bước lifecycle, source “Không thay đổi”, không tràn ngang tại viewport 1280 px.

# IMMEDIATE-007 — Progress, structured logging và lỗi ổn định

## Gọi Python API với progress và JSONL log

`progress` là keyword-only callback và nhận đúng một `ProgressEvent`. Ví dụ tối thiểu:

```python
import logging
import sys
from pathlib import Path

from src.relay_form_ocr import JsonLineFormatter, OcrRequest, RelayFormOcrService

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(JsonLineFormatter())
logger = logging.getLogger("relay_form_ocr.consumer")
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

events = []
service = RelayFormOcrService(logger=logger)
result = service.process_pdf(
    OcrRequest(
        input_pdf=Path(r"D:\management-data\P_003.pdf"),
        output_root=Path(r"D:\ocr-artifacts"),
        correlation_id="ticket-123",
    ),
    progress=events.append,
)
print(result.status, events[-1].completed, events[-1].total)
```

Mỗi event có `correlation_id`, `stage`, `event`, `completed`, `total`, `message`,
optional `page_number` và `terminal`. `total` cố định 100, `completed` tăng đơn điệu.
Success có đúng một terminal event `100/100`; failure có terminal event tại tiến độ
thật gần nhất. Nếu callback ném exception, service vô hiệu callback sau lỗi đầu tiên,
ghi `progress_callback_failed` và tiếp tục OCR; không dùng callback để điều khiển hoặc
hủy pipeline.

CLI tự cấu hình cùng JSONL logger trên stderr. Stdout vẫn chỉ chứa machine result JSON
hoặc rỗng khi có `--output-json`; không parse progress từ stdout.

## Error stage, retryability và dữ liệu nhạy cảm

Catalog chính thức nằm ở `contracts/local_api/v1/error_catalog.json`. Schema v1 giữ
nguyên 12 `ErrorCode` và các stage `validation`, `rendering`, `detection`,
`recognition`, `layout`, `artifact_write`, `pipeline`. Caller quyết định retry bằng
`error.retryable`, không suy luận từ message. Collision, path/reparse/security và
request sai không retry; lỗi render/model/ghi tạm thời có thể retry theo catalog.

Mặc định log không có input/output path, tên PDF, OCR text, exception message,
traceback hoặc stack. Chỉ bật `RelayFormOcrService(include_exception_trace=True)`
trong môi trường debug riêng tư có kiểm soát; tuyệt đối không gửi log đó cho caller.
Public result luôn được khử dữ liệu nhạy cảm dù private trace có bật.

## Ranh giới khi sửa đổi

1. Sửa cấu trúc, formatter hoặc callback policy trong
   `src/relay_form_ocr/observability.py`; giữ `ProgressEvent` bất biến và monotonic.
2. Sửa điểm phát event nội bộ hoặc stage wrapping trong
   `src/relay_form_ocr/orchestrator.py`; không đổi callback ba đối số của Debug UI.
3. Sửa mapping progress/result/error public trong `src/relay_form_ocr/service.py`.
4. Sửa stream/wiring subprocess trong `src/relay_form_ocr/cli.py`; stdout không được
   lẫn log hay progress.
5. Khi đổi code/stage/retryability, cập nhật đồng thời `schemas.py`,
   `contracts/local_api/v1/error_catalog.json`, contract manifest, tài liệu và tests.

## Chạy test progress, logging và error mapping

Focused suite:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_local_api_observability -v
```

Combined regression suite:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" -m unittest `
  tests.test_local_api_observability `
  tests.test_workspace_isolation `
  tests.test_local_api_service `
  tests.test_local_api_cli `
  tests.test_local_api_models `
  tests.test_local_api_contract `
  tests.test_document_orchestrator -v
```

Full repository verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

## Sinh test trực quan tiếng Việt

Sinh report demo nhanh, không tải model OCR:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.observability_visual `
  --output ".\output\local_observability\observability_review_demo.html"
```

Chạy E2E thật và đồng thời lưu progress trace, JSONL log, typed result và report:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.observability_visual `
  --input-pdf ".\data\pdf_split\documents\P_003.pdf" `
  --output-root ".\output\local_observability\kết-quả" `
  --correlation-id "immediate-007-p003" `
  --logs ".\output\local_observability\structured_log.jsonl" `
  --trace-output ".\output\local_observability\progress_trace.json" `
  --result-json ".\output\local_observability\public_result.json" `
  --output ".\output\local_observability\observability_review.html"
```

Nếu OCR đã chạy, dựng lại report mà không chạy model:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.observability_visual `
  --trace ".\output\local_observability\progress_trace.json" `
  --logs ".\output\local_observability\structured_log.jsonl" `
  --output ".\output\local_observability\observability_review.html"
```

Mở bằng local HTTP nếu browser chặn `file://`:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m http.server 8768 `
  --bind 127.0.0.1 `
  --directory ".\output\local_observability"
```

Mở `http://127.0.0.1:8768/observability_review.html`, kiểm tra timeline tăng đơn
điệu, terminal 100/100, đủ 12 error codes, nội dung tiếng Việt có dấu và không lộ
path/OCR text. Nhấn `Ctrl+C` để dừng server. Browser QA ngày 2026-07-30 ở viewport
1280 px xác nhận 59 dòng progress, đủ 12 error codes, không `None`, duplicate DOM hay
tràn ngang.

# IMMEDIATE-008 — Consumer example và integration harness

## Contract quyết định của consumer

Reference implementation nằm trong `examples/local_consumer/` và không import
orchestrator, workspace, Debug UI hoặc module private. Consumer luôn validate typed
result rồi kiểm tra physical manifest/artifacts trước khi trả quyết định:

| Outcome | Exit | Ý nghĩa |
|---|---:|---|
| `ready_for_use` | `0` | OCR thành công và `review_status=not_required`. |
| `manual_review_required` | `10` | OCR thành công nhưng bắt buộc người duyệt; không phải approved. |
| `failed` | `20` | OCR trả public error code/stage/retryable. |
| `consumer_failure` | `21` | Schema, stream, path, manifest, size hoặc checksum không hợp lệ. |
| invalid consumer request | `2` | Tham số consumer không tạo được `OcrRequest`. |

Page 3+, `Lưu ý`, warning hoặc bất kỳ `review_required` nào đều không được tự động
ghi vào dữ liệu chính thức. Summary chỉ chứa version, correlation ID, status/review,
counts, audit/progress và public error code/stage/retryable; không chứa absolute path,
OCR text, exception message hay traceback.

## Chạy Python consumer từ thư mục riêng

Source checkout hiện chưa phải installable package, vì vậy thêm repository root vào
`PYTHONPATH`. Đây chỉ là bootstrap cho source checkout; packaging chính thức thuộc
kế hoạch deployment sau.

```powershell
$projectRoot = (Resolve-Path ".").Path
$pythonExe = Join-Path $projectRoot "lab\structure_analysis_2\.venv\Scripts\python.exe"
$env:PYTHONPATH = $projectRoot

Push-Location "D:\management-consumer"
& $pythonExe -m examples.local_consumer.python_consumer `
  --input "D:\management-data\P_003.pdf" `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "management-ticket-123" `
  --summary-json "D:\management-consumer\ocr-summary.json"
$consumerExit = $LASTEXITCODE
Pop-Location
```

Consumer cô lập output do Python/model library ghi ở cả Python stream và native file
descriptor sang stderr. Machine stdout chỉ có đúng một sanitized summary JSON. Exit
`10` là outcome nghiệp vụ dự kiến khi cần review, không phải crash. Mỗi lần chạy phải
dùng correlation ID mới vì workspace tồn tại luôn là collision.

## Chạy PowerShell/subprocess consumer

Adapter PowerShell gọi public `python -m src.relay_form_ocr`, tách stderr, parse
`OcrResult`, kiểm tra artifact rồi xuất cùng loại sanitized summary:

```powershell
$projectRoot = "C:\Users\tinhv\MyProject\A_WORK\OCR_PRJ"
& "$projectRoot\examples\local_consumer\invoke_ocr.ps1" `
  -InputPdf "D:\management-data\P_003.pdf" `
  -OutputRoot "D:\ocr-artifacts" `
  -CorrelationId "management-ticket-124" `
  -ProjectRoot $projectRoot `
  -PythonExe "$projectRoot\lab\structure_analysis_2\.venv\Scripts\python.exe"
$consumerExit = $LASTEXITCODE
```

Không parse model/log stderr thành result. Chỉ stdout JSON và exit convention ở bảng
trên được dùng làm consumer contract.

## Ranh giới khi sửa đổi

1. Sửa direct-call, summary, review gate hoặc integrity audit trong
   `examples/local_consumer/python_consumer.py`.
2. Sửa subprocess/PowerShell mapping trong `invoke_ocr.ps1`; giữ public CLI entry point
   và không đưa stderr/raw exception vào summary.
3. Sửa report trong `consumer_visual.py`; mọi nhãn/giải thích cho người review phải là
   tiếng Việt có dấu.
4. `ready_for_use` chỉ được giữ khi cả processing và review gate đều đạt; không hạ
   `review_required` thành ready chỉ vì OCR trả success.
5. Mọi thay đổi outcome/exit/summary phải cập nhật contract, focused tests và tài liệu.
6. Không import `src.relay_form_ocr.service`, `.workspace`, `.orchestrator`, Debug UI
   hoặc đọc marker nội bộ. Consumer chỉ dựa vào public models và public artifact data.

## Chạy test consumer

Focused suite:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_local_consumer_harness -v
```

Combined local integration regression:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" -m unittest `
  tests.test_local_consumer_harness `
  tests.test_local_api_observability `
  tests.test_workspace_isolation `
  tests.test_local_api_service `
  tests.test_local_api_cli `
  tests.test_local_api_models `
  tests.test_local_api_contract `
  tests.test_document_orchestrator -v
```

Full repository verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

## E2E thật từ external working directory

Command đã dùng cho `P_003.pdf`; đổi correlation ID/output khi tái chạy:

```powershell
$projectRoot = (Resolve-Path ".").Path
$env:PYTHONPATH = $projectRoot
$externalCwd = Join-Path $projectRoot "output\local_consumer\external_cwd"
New-Item -ItemType Directory -Force -Path $externalCwd | Out-Null

Push-Location $externalCwd
& "$projectRoot\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m examples.local_consumer.python_consumer `
  --input "$projectRoot\data\pdf_split\documents\P_003.pdf" `
  --output-root "$projectRoot\output\local_consumer\kết-quả" `
  --correlation-id "immediate-008-p003-rerun" `
  --summary-json "$projectRoot\output\local_consumer\consumer_summary_rerun.json"
Pop-Location
```

Run ngày 2026-07-30 hoàn tất trong 350.7 giây với
`success_with_warnings/review_required` → `manual_review_required`: 8 trang, 7
warnings, 18/18 public artifacts verified, 17 physical payload artifacts đúng
size/checksum, source bất biến và 59 progress events với đúng một terminal 100/100.

## Sinh và mở test trực quan tiếng Việt

Report demo nhanh:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m examples.local_consumer.consumer_visual `
  --output ".\output\local_consumer\consumer_review_demo.html"
```

Report từ summary thật:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m examples.local_consumer.consumer_visual `
  --summary ".\output\local_consumer\consumer_summary.json" `
  --output ".\output\local_consumer\consumer_review.html"
```

Mở qua local HTTP nếu browser chặn `file://`:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m http.server 8769 `
  --bind 127.0.0.1 `
  --directory ".\output\local_consumer"
```

Mở `http://127.0.0.1:8769/consumer_review.html`; kiểm tra năm bước, outcome review,
manifest/source/progress và hàng rào không auto-approve. Browser QA ngày 2026-07-30
ở viewport 1265 px xác nhận đúng dữ liệu E2E, không absolute path, duplicate DOM,
tràn ngang hoặc console warning/error. Nhấn `Ctrl+C` để dừng server.

# IMMEDIATE-009 — Per-PDF acceptance run

Phần này chạy từng PDF qua đúng public `RelayFormOcrService`, ghi evidence có thể
resume/audit và không dùng API nội bộ. Acceptance xác nhận contract, độ ổn định,
workspace/artifact và review gate; nó không xác nhận độ chính xác OCR khi chưa có
ground truth.

Các thành phần chính:

- `contracts/local_api/v1/acceptance_corpus.json`: corpus và layout family.
- `examples/local_consumer/acceptance_runner.py`: `plan`, `run`, `resume`, `verify`.
- `examples/local_consumer/acceptance_visual.py`: report HTML tiếng Việt độc lập.
- `tests/test_pdf_acceptance.py`: contract, repeatability, resume, GPU preflight,
  artifact audit và report regressions.

## Sửa hoặc mở rộng corpus

Mỗi case thật trong `acceptance_corpus.json` cần `id`, `layout_family`,
`relative_pdf`, `expected_page_count` và `repeat`. `relative_pdf` phải nằm dưới
`--input-root`; không ghi absolute path vào corpus. Để tăng lên khoảng 30 PDF,
thêm từng case với `id` duy nhất, family đã có hoặc family mới, rồi chạy `plan`
trước khi OCR. Dùng `repeat: 2` cho ít nhất một case cần kiểm tra repeatability.

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m examples.local_consumer.acceptance_runner plan `
  --corpus ".\contracts\local_api\v1\acceptance_corpus.json" `
  --input-root ".\data\pdf" `
  --device cpu
```

`plan` kiểm tra schema corpus, file/page count, runtime và device nhưng không chạy
OCR hoặc tạo workspace acceptance. Nếu chọn GPU, cả PyTorch CUDA và Paddle CUDA
phải sẵn sàng; preflight dừng sớm với exit code 40 nếu một runtime không dùng được.
Public Python API bật GPU bằng `RelayFormOcrService(use_gpu=True)`.

## Chạy, tiếp tục và kiểm tra acceptance

Chạy CPU trên máy hiện tại:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m examples.local_consumer.acceptance_runner run `
  --corpus ".\contracts\local_api\v1\acceptance_corpus.json" `
  --input-root ".\data\pdf" `
  --output-root ".\output\local_acceptance" `
  --run-id "immediate-009-cpu-20260731" `
  --device cpu
```

Trên PC có đúng CUDA runtime, đổi `--device cpu` thành `--device gpu` và dùng một
`--run-id` mới. Khi một run bị ngắt, chạy lại cùng lệnh kèm `--resume`; runner giữ
những execution đã hoàn tất và tiếp tục case còn thiếu. Không dùng `--resume` để
trộn corpus, device hoặc revision khác với manifest đã tạo.

Xác minh evidence sau khi chép từ máy khác hoặc trước khi nghiệm thu:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m examples.local_consumer.acceptance_runner verify `
  --manifest ".\output\local_acceptance\immediate-009-cpu-20260731\acceptance_manifest.json" `
  --full-artifact-audit
```

Mỗi run có manifest tổng, report, execution evidence và compact copy của physical
artifact manifest. Không sửa evidence thủ công; tạo run ID mới nếu corpus/runtime
thay đổi. Exit code: 0 đạt, 30 có case không đạt, 31 evidence không hợp lệ, 40 GPU
không sẵn sàng và 2 là lỗi cấu hình.

## Sinh và chạy test trực quan tiếng Việt

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m examples.local_consumer.acceptance_visual `
  --manifest ".\output\local_acceptance\immediate-009-cpu-20260731\acceptance_manifest.json" `
  --output ".\output\local_acceptance\immediate-009-cpu-20260731\acceptance_review.html"

& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m http.server 8770 `
  --bind 127.0.0.1 `
  --directory ".\output\local_acceptance\immediate-009-cpu-20260731"
```

Mở `http://127.0.0.1:8770/acceptance_review.html`, kiểm tra đủ family/case,
repeatability, failure contract, warnings/review status và hàng rào không tuyên bố
accuracy. Nhấn `Ctrl+C` để dừng server.

## Câu lệnh kiểm thử

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" -m unittest `
  tests.test_pdf_acceptance `
  tests.test_local_consumer_harness `
  tests.test_local_api_observability `
  tests.test_workspace_isolation `
  tests.test_local_api_service `
  tests.test_local_api_cli `
  tests.test_local_api_models `
  tests.test_local_api_contract `
  tests.test_document_orchestrator -v

powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Run nghiệm thu ngày 2026-07-31 đạt 10/10 executions trên 8/8 layout families:
69 trang thật, 65 warnings, 156 public artifacts, source bất biến, full checksum
audit, không workspace collision, C264 lặp ổn định và PDF hỏng trả `INVALID_PDF`.
Tổng elapsed được ghi là 3065.1 giây. Cả 9 run thật đều
`success_with_warnings/review_required`; cần người review và không được diễn giải
thành accuracy. Browser QA report ở 1280 px và 390 px không thấy path nội bộ,
duplicate ID, tràn trang hoặc console warning/error.

# IMMEDIATE-010 — Handoff và khóa Local API v1

Local API/schema/CLI được khóa ở `1.0`; pipeline implementation hiện là `0.7.0`.
Các tài liệu bàn giao chính:

- `README.md`: điểm bắt đầu nhanh và phạm vi hỗ trợ.
- `API.md`: hướng dẫn chi tiết cho team clone repo và tích hợp Python/CLI.
- `ARCHITECTURE.md`: data flow, package boundaries, review gate và Trust boundary.
- `docs/LOCAL_API_CONTRACT_V1.md`: contract request/result/error chuẩn.
- `contracts/local_api/v1/release_manifest.json`: release state máy đọc được.
- `session-handoff.md`: trạng thái, evidence, risk và task tiếp theo.

## Quy tắc sửa đổi

Khi thêm optional field mà vẫn giữ v1:

1. Cập nhật typed model và fixture cũ/mới.
2. Export lại deterministic JSON Schema.
3. Chứng minh consumer/fixture v1 cũ vẫn validate.
4. Cập nhật release manifest, `API.md`, contract và test handoff.

Xóa/rename field, đổi type/nullability, enum/error semantics, review gate hoặc
artifact path boundary là breaking change và phải tăng major API/schema. Không chỉ
đổi tài liệu mà giữ schema version cũ. `pipeline_version` có thể tăng độc lập nếu
result vẫn validate theo declared schema.

Public imports được release manifest kiểm tra phải tồn tại trong
`src.relay_form_ocr`. Không hướng dẫn consumer import `service.py`, `schemas.py`,
orchestrator, workspace implementation hoặc debug/lab package trực tiếp.

## Chạy handoff validator và focused tests

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m scripts.local_api_v1_handoff --check-only

& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m unittest tests.test_local_api_handoff -v
```

Validator kiểm tra version constants, contract manifest, public imports, file/link,
tracked JSON Schema, bốn typed fixtures, acceptance summary, safety evidence và
PLAN-001 là task tiếp theo. Focused tests còn chạy public import, CLI help và typed
invalid-PDF failure từ external Unicode cwd.

## Smoke test theo tài liệu từ thư mục consumer riêng

```powershell
$projectRoot = (Resolve-Path ".").Path
$pythonExe = "$projectRoot\lab\structure_analysis_2\.venv\Scripts\python.exe"
$consumerDir = Join-Path $env:TEMP "consumer ngoài repository"
New-Item -ItemType Directory -Force -Path $consumerDir | Out-Null
$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $projectRoot
  } else {
    $projectRoot + [System.IO.Path]::PathSeparator + $previousPythonPath
  }
  Push-Location $consumerDir
  & $pythonExe -c `
    "from src.relay_form_ocr import OcrRequest, OcrResult, RelayFormOcrService, ProgressEvent, PIPELINE_VERSION; print(PIPELINE_VERSION)"
  & $pythonExe -m src.relay_form_ocr --help
  Pop-Location
} finally {
  $env:PYTHONPATH = $previousPythonPath
}
```

Smoke test chỉ kiểm tra public import/CLI documentation contract, không load model
hoặc OCR lại corpus.

## Sinh test trực quan tiếng Việt

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m scripts.local_api_v1_handoff `
  --output ".\output\local_api_handoff\handoff_review.html"

& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m http.server 8771 `
  --bind 127.0.0.1 `
  --directory ".\output\local_api_handoff"
```

Mở `http://127.0.0.1:8771/handoff_review.html`. Kiểm tra version, 8 layout
families, 10/10 executions, supported scope, limitations, đủ file handoff, hàng rào
không tuyên bố accuracy và task tiếp theo PLAN-001. Kiểm tra cả desktop/mobile;
nhấn `Ctrl+C` để dừng server.

## Xác minh đầy đủ trước khi bàn giao

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" -m compileall -q `
  scripts\local_api_v1_handoff.py `
  tests\test_local_api_handoff.py `
  src\relay_form_ocr `
  examples\local_consumer

& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" -m pip check

powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Nếu evidence IMMEDIATE-009 còn trên máy, audit lại mà không OCR corpus:

```powershell
& ".\lab\structure_analysis_2\.venv\Scripts\python.exe" `
  -m examples.local_consumer.acceptance_runner verify `
  --manifest ".\output\local_acceptance\immediate-009-cpu-20260731\acceptance_manifest.json" `
  --full-artifact-audit
```

Clean clone không có `output/` vì artifacts bị Git ignore; cần chạy acceptance mới
hoặc nhận evidence bundle từ máy nghiệm thu nếu muốn chạy lệnh audit cuối.

Run IMMEDIATE-010 ngày 2026-07-31: validator hợp lệ, 8/8 focused handoff tests,
64/64 combined contract tests và 257/257 full tests pass; acceptance evidence vẫn
đạt 10/10 với full artifact audit. Browser QA của report tiếng Việt ở 1280×720 và
390×844 xác nhận không tràn ngang, duplicate ID, absolute Windows path, `None` hoặc
console warning/error. Local clone sạch của commit `fbade92` cũng chạy 8/8 handoff
tests và giữ worktree sạch.
