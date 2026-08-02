# Kế hoạch tích hợp ngay OCR_PRJ trên cùng một server

Ngày lập kế hoạch: 2026-07-29

## Mục tiêu

Tạo sớm một **local application API** để hệ thống quản lý phiếu và OCR_PRJ chạy trên cùng một máy có thể tích hợp trực tiếp. Giai đoạn này chỉ xử lý **một file PDF_x cho mỗi lần gọi**.

API trong tài liệu này không phải HTTP API. Hướng tích hợp chính là:

1. Python API gọi trực tiếp nếu hệ thống quản lý cũng chạy Python.
2. Local CLI trả JSON nếu hệ thống quản lý dùng ngôn ngữ/runtime khác.

## Phạm vi trước mắt

- Input: đúng một đường dẫn tới file PDF_x có sẵn trên cùng server.
- Xử lý: đồng bộ; lời gọi chỉ trả về sau khi PDF xử lý xong hoặc thất bại.
- Output: một result object/JSON theo schema ổn định và artifacts trong workspace riêng.
- Chỉ một máy, không network transport, không HTTP, không upload multipart.
- Chưa xử lý PDF_A nhiều phiếu trong public API trước mắt.
- Chưa triển khai queue, nhiều worker, distributed storage, webhook hoặc multi-tenant.
- Kết quả Page 3+ vẫn phải được đánh dấu là candidate/review-required cho đến khi có ground-truth metrics đạt ngưỡng.

## Public interface mục tiêu

Python caller dự kiến dùng theo dạng:

```python
from pathlib import Path
from src.relay_form_ocr import OcrRequest, RelayFormOcrService

service = RelayFormOcrService()
result = service.process_pdf(
    OcrRequest(
        input_pdf=Path(r"D:\management-data\P_001.pdf"),
        output_root=Path(r"D:\ocr-artifacts"),
        correlation_id="ticket-123",
    )
)

payload = result.model_dump(mode="json")
```

Nếu caller không phải Python, local CLI dự kiến dùng theo dạng:

```powershell
& ".\.venv\Scripts\python.exe" -m src.relay_form_ocr `
  --input "D:\management-data\P_001.pdf" `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-123" `
  --json
```

CLI phải ghi machine-readable JSON vào stdout, log vào stderr và trả exit code ổn định.

## Quy ước trạng thái

- **Chưa làm**: chưa bắt đầu implementation của task.
- **Đã hoàn thành**: implementation đạt đủ hành vi, tất cả test bắt buộc pass và Acceptance Evidence đã được ghi.
- **Đã làm nhưng chưa được coi là hoàn thành vì một vài lý do nhỏ**: phần chính đã có nhưng còn thiếu phạm vi, test, tài liệu hoặc bằng chứng bắt buộc.
- **Đã làm nhưng lỗi**: implementation đã có nhưng hành vi sai, test bắt buộc fail hoặc gây regression.

Mặc định mọi task dưới đây là **Chưa làm**. Agent thực hiện task nào phải cập nhật trạng thái và Acceptance Evidence của chính task đó trước khi chuyển sang task tiếp theo.

## Trạng thái tổng

- **Task đang thực hiện:** Chưa có; toàn bộ IMMEDIATE-001A–010 đã hoàn thành.
- **Task tiếp theo:** PLAN-001 — Chốt phạm vi nghiệp vụ và ranh giới tích hợp.
- **Blocker hiện tại:** Không có blocker trong phạm vi local integration v1. Module chưa production-ready vì còn thiếu ground truth/quality gates, installable packaging/deployment, trust boundary, capacity test và UAT theo `plan.md`; source checkout vẫn cần repository root trên `PYTHONPATH`.
- **Ngoài phạm vi:** HTTP/FastAPI, API qua mạng, nhiều PDF trong một call, queue phân tán và production auto-accept.

---

## IMMEDIATE-001A — Registry schema, loader và append-only merge

**Công việc cần làm**

Tạo JSON registry có version cho field aliases, topology hints, anchors, value rules và scoring config. Loader phải đọc registry mặc định trong repo, nhận optional user overlay, hợp nhất alias/value rule theo kiểu append-only, không cho overlay xóa hoặc ghi đè built-in rules, giữ provenance và cho phép user rule có trạng thái `active/disabled`. Hai ngưỡng `auto_select_minimum: 70` và `winner_margin_minimum: 15` phải nằm trong registry.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test: load registry mặc định và đọc đúng hai ngưỡng 70/15.
- Unit test: user alias được append mà built-in aliases vẫn nguyên vẹn.
- Unit test: mọi active alias được giữ để engine sau này kiểm tra hết; alias trùng giữa nhiều canonical fields không bị loader tự loại.
- Unit test: user value rule như `unit_suffix=A` được append và giữ provenance.
- Validation test: schema version, field name, alias, status, scoring range và malformed JSON.
- Security/config test: overlay không được khai báo built-in origin hoặc xóa/replace rules mặc định.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-29. `field_rules.json` chứa schema version 1.0, weights tổng 100, `auto_select_minimum=70`, `winner_margin_minimum=15`, toàn bộ aliases hiện có và các aliases human đã xác nhận. `rules.py` cung cấp immutable-style dataclasses, normalization, registry/overlay validation, append-only merge, provenance, active/disabled status và conflict lookup giữ cùng alias ở nhiều canonical fields.
- User overlay chỉ được append vào canonical fields đã tồn tại; không thể khai `built_in`, dùng replace directive, tạo field lạ hoặc âm thầm chấp nhận schema/status/scoring sai. User value rules và aliases giữ `created_by`; scoring thresholds có thể tune qua overlay mà không sửa code.
- Acceptance tests: 9 focused registry tests pass; compileall cho Page-1 package/tests pass; full `init.ps1` pass 85 tests. Default-registry test chứng minh mọi alias trong `FIELD_SPECS` vẫn được bảo toàn, nên task này chưa thay đổi hành vi extractor.
- Environment note: root `.venv` vẫn trỏ tới Python đã bị gỡ; focused tests dùng `lab\structure_analysis_2\.venv`, và standard `init.ps1` fallback vẫn pass. Đây không chặn task nhưng cần `scripts\setup_debug_ui.ps1 -RecreateVenv` trước E2E model/UI nếu root runtime được dùng.

## IMMEDIATE-001B — Candidate scoring engine và năm confidence levels

**Công việc cần làm**

Tạo engine độc lập nhận field candidates và score breakdown theo topology, anchor, alias, separator, value validation và OCR confidence. Engine phải đọc weights/ngưỡng từ registry, ánh xạ score sang năm confidence levels, áp dụng hard caps và tự chọn winner khi điểm cao nhất ít nhất 70, hơn candidate thứ hai ít nhất 15 và không vi phạm hard constraints.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test từng thành phần điểm và năm confidence levels.
- Unit test thiếu `:` không bị trừ điểm; có `:` hợp lệ được cộng bonus.
- Unit test hard value validator fail giới hạn tối đa mức 2.
- Unit test winner 70/margin 15 được chọn; dưới threshold hoặc margin trả `review_required`.
- Config test: thay thresholds/weights trong fixture làm thay đổi quyết định mà không sửa code.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30. `scoring.py` cung cấp engine độc lập, immutable-style candidate/evidence/result objects, score breakdown cho đủ sáu component, raw/effective score, năm confidence levels (`very_low` đến `very_high`), generic hard caps và helper hard value validator cap ở level 2. Engine đọc weights, `auto_select_minimum` và `winner_margin_minimum` trực tiếp từ registry; không tích hợp hay thay đổi extractor production trong task này.
- Decision evidence ghi leading/selected/runner-up candidate, margin, thresholds và lý do `auto_selected`/`review_required`. Winner đúng ngưỡng 70 và margin 15 được chọn; dưới threshold, thiếu margin hoặc có hard constraint đều cần review. Tie được sắp xếp ổn định theo `candidate_id`, nên kết quả không phụ thuộc thứ tự input/alias.
- Mười focused scoring tests pass, gồm từng component, đủ năm levels, separator bonus không có penalty, hard validator cap, exact 70/15, below-threshold/margin, config-driven weights/thresholds, deterministic tie và HTML renderer. Chín registry tests vẫn pass; compileall pass; full `init.ps1` pass toàn bộ 95 tests.
- `scoring_visual.py` đã sinh thành công `output/page1_scoring/scoring_review.html` với score bars, raw/effective score, confidence, hard cap, margin và decision. `manual.md` ghi cách sửa overlay, chạy focused/full tests và sinh HTML từ fixture riêng. Automated browser review của file local không chạy được vì in-app browser chặn `file://`; HTML structure/content được unit-test và file sẵn sàng để human mở thủ công. Đây là giới hạn QA trực quan tùy chọn, không chặn các test bắt buộc của IMMEDIATE-001B.
- Root `.venv` vẫn stale và `python` không có trên PATH trong focused run; focused tests/visual CLI dùng `lab\structure_analysis_2\.venv`, còn standard `init.ps1` tự dùng fallback và pass. Cần `scripts\setup_debug_ui.ps1 -RecreateVenv` trước E2E model/UI về sau.

## IMMEDIATE-001C — Topology và anchor relationship resolver

**Công việc cần làm**

Tạo resolver dùng field đã nhận diện làm anchor cho field candidate xung quanh theo `above/below/left/right/same_row/same_column`, khoảng cách tương đối theo text height và table/header topology. Bổ sung quan hệ hai chiều giữa ticket number và page reference, đồng thời giữ structure-first ownership của Table 01.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test mọi relation và normalized-distance rule trên nhiều DPI/page size.
- Unit test page reference làm anchor tìm ticket phía trên trong header phải.
- Unit test ticket làm context kiểm tra page reference như hành vi hiện tại.
- Unit test relay name làm anchor chọn relay version cùng hàng/bên phải.
- Negative test: candidate sai region/cell bị hard cap và không lấy block của field khác.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30. `relationships.py` cung cấp resolver độc lập cho `above/below/left/right/same_row/same_column/same_row_right`, chuẩn hóa edge gap và alignment theo chiều cao chữ trung bình, kiểm tra page coordinate space và cho phép tune tolerance qua `RelationshipPolicy` mà không đưa pixel threshold vào thuật toán.
- Resolver đọc active `page_region`, `cover_slot` và `field_relation` rules trực tiếp từ registry. Ticket/page-reference được kiểm tra hai chiều trong right header; relay version dùng relay name làm anchor cùng hàng bên phải. Kết quả giữ topology/anchor score, matched anchor, normalized distance, alignment, overlap, reason, eligibility và hard constraints để chuyển thẳng sang scoring engine ở task tích hợp sau.
- Candidate có source cell/page region rõ ràng nhưng sai bị `topology_mismatch`, hard-cap confidence level 2 và không eligible; candidate thiếu source-cell evidence là `not_evaluated`, không bị false hard failure. Negative scoring test chứng minh wrong Table-01 owner bị cap dưới 40 và không thắng correct owner.
- Mười focused relationship tests pass; combined resolver/scoring/Page-1 regression suite pass 41 tests, gồm mọi relation, direction/distance failure, scale 0.5x–4x, header hai chiều, relay version, wrong header region, wrong Table-01 cell, missing-cell behavior và HTML/SVG structure. Compileall pass; full `init.ps1` pass toàn bộ 105 tests. Extractor production không bị nối/thay đổi trong task này và structure-first Table 01 regressions vẫn pass.
- `relationship_visual.py` đã sinh `output/page1_relationships/relationship_review.html` gồm bbox, anchor line, normalized distance, topology match/mismatch, score và hard-cap cases. `manual.md` được nối thêm (không ghi đè) với policy tuning, focused/full commands, visual CLI và custom fixture schema.
- Root `.venv` vẫn stale và `python` không có trên PATH; focused/visual commands dùng `lab\structure_analysis_2\.venv`, còn `init.ps1` fallback pass. Không có blocker cho task kế tiếp; cần recreate root venv trước E2E model/UI nếu dùng runtime đó.

## IMMEDIATE-001D — Alias, dấu hai chấm và configurable value validators

**Công việc cần làm**

Tích hợp toàn bộ active aliases trong registry, longest/specific-match handling, tách phần trái/phải dấu `:` và value validators cấu hình. Hỗ trợ tối thiểu `unit_suffix/endswith`, `startswith`, `regex`, `enum`, `numeric`, `numeric_range`, `version` và `ticket_number`. Bổ sung các alias đã xác nhận: `Nguyên nhân thay đổi chỉnh định`, `Mục đích ban hành phiếu`, `Số`, `Phiên bản rơ-le`.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test mọi validator type và invalid rule configuration.
- Unit test `Ampe: 20A` pass, `Ampe: 20 A` normalize đúng và `Ampe: 20V` bị hard cap mức 2.
- Unit test `Số:` không nhầm với `Số hiệu`, `Số trang`, `Số lượng`.
- Unit test có/không có `:` và OCR block label/value bị split/merge.
- Unit test cùng alias cho nhiều fields được resolver chấm mọi candidate, không chọn theo thứ tự cấu hình.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30. `value_resolution.py` cung cấp resolver độc lập đọc toàn bộ active aliases từ registry, so khớp không phân biệt hoa/thường và dấu, giữ nguyên OCR text/provenance, ưu tiên alias dài/cụ thể nhất tại cùng vị trí và giữ mọi canonical field khi một alias được dùng chung. Resolver xử lý `:`/`：`, không phạt khi thiếu dấu, ghép label/value qua các OCR block logic liền nhau và giữ source block indices trong evidence.
- Guard cho alias ngắn `Số` không nhận nhầm `Số hiệu`, `Số trang`, `Số lượng`; alias nằm trong value text không bị coi là label mới nếu không có separator. Toàn bộ active aliases mặc định đều được fixture duyệt; disabled overlay alias bị bỏ qua; các alias đã xác nhận `Nguyên nhân thay đổi chỉnh định`, `Mục đích ban hành phiếu`, `Số`, `Phiên bản rơ-le` đều có trong registry và được resolver kiểm tra.
- Validator cấu hình hỗ trợ `unit_suffix`, `endswith`, `startswith`, `regex` full-match, `enum`, `numeric`, `numeric_range` inclusive, `version`, `ticket_number`, đồng thời tương thích với `year` và `page_reference` đang có. Cấu hình sai bị từ chối sớm; `20A`/`20 A` cùng pass và normalize, còn required validator fail như `20V` tạo hard-cap confidence level 2 chuyển trực tiếp được vào scoring engine.
- Mười ba focused tests pass; combined value-resolution/registry/scoring/relationship/Page-1 regression suite pass 63 tests; compileall và `git diff --check` pass; full `init.ps1` pass toàn bộ 118 tests. Extractor production chưa bị nối/thay đổi trong task này và được dành cho IMMEDIATE-001E.
- `value_resolution_visual.py` đã sinh `output/page1_value_resolution/value_resolution_review.html` với 7 alias cases và 6 validator cases; toàn bộ nhãn/giải thích hiển thị là tiếng Việt có dấu, và renderer/hard-cap content có unit test. `manual.md` được nối thêm ở cuối, không ghi đè hai chương cũ, gồm quy ước, overlay, focused/full commands, visual CLI và custom fixture schema.
- Root `.venv` vẫn stale và `python` không có trên PATH; focused/visual commands dùng `lab\structure_analysis_2\.venv`, còn standard `init.ps1` fallback pass. Không có blocker cho IMMEDIATE-001E; cần recreate root venv trước E2E model/UI nếu dùng runtime đó.

## IMMEDIATE-001E — Tích hợp Page 1, regression và field-resolution evidence

**Công việc cần làm**

Tích hợp registry/resolvers/scoring vào Page 1 production pipeline, giữ output schema tương thích và bổ sung evidence gồm resolution method, matched rule, anchor, score breakdown, confidence level và winner margin. Chạy regression hiện có và E2E trên OCR/PDF thật nếu có dữ liệu biến thể.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Integration test cho ba nhóm label thay đổi đã được human xác nhận.
- Regression test toàn bộ Page 1 và debug UI orchestration hiện có.
- E2E test trên PDF/OCR payload thật có label biến thể khi dữ liệu sẵn có.
- Backward-compatibility test cho canonical field names và existing consumers.
- Full repository verification bằng `init.ps1`.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30. Page 1 production pipeline đã nối registry, alias/separator resolver, topology/anchor resolver, configurable value validators và candidate scoring engine. Output vẫn giữ `schema_version: 1.1`, đủ 25 canonical keys trong `fields`, `source_labels` và hành vi structure-first; evidence mới được bổ sung ở top-level `field_resolution` cho từng field với resolution method, matched rule, anchor/topology, value validation, score breakdown, raw/effective score, năm mức confidence, winner margin và decision.
- Existing non-null values không bị ghi đè. Null field chỉ được bổ sung khi candidate đạt ngưỡng 70, margin 15 và vượt hard constraints; Table-01 structure-owned null luôn được bảo toàn, còn cover-field null phải có cover-slot topology hoặc anchor khớp. Required validator failure bị cap ở confidence level 2. Service nhận optional registry hoặc append-only overlay mà không phá constructor cũ.
- Mười bốn focused integration tests pass, gồm ba nhóm label đã xác nhận, split label/value, invalid version hard-cap, competing candidates, structure/cover ownership, schema/consumer compatibility, overlay và renderer tiếng Việt có dấu. Combined Page-1/debug suite pass 85 tests; compileall và `git diff --check` pass; full `init.ps1` pass toàn bộ 132 tests.
- Real-data before/after audit trên 19 cached Page-1 OCR payload đạt 19/19 compatible, 0 canonical key change, 0 existing non-null value change và 0 unsafe supplement. Dữ liệu thật phủ `Số` và `Mục đích ban hành phiếu` trên 19/19 mẫu, `Phiên bản rơ-le` trên 1/19; chưa có mẫu thật cho `Nguyên nhân thay đổi chỉnh định`, nên biến thể này được chứng minh bằng synthetic integration fixture. Real PDF E2E `P_003.pdf --reuse-ocr` xử lý đủ 8 trang, giữ 25 fields, không warning và không auto-apply candidate thiếu ownership.
- `field_resolution_visual.py` đã sinh `output/page1_field_resolution/field_resolution_review.html` với nội dung tiếng Việt có dấu; `field_resolution_audit.py` sinh `real_data_audit.json`. `manual.md` được nối thêm ở cuối, không ghi đè, gồm contract/evidence, safety policy, overlay, test, visual và real-audit commands.
- Root `.venv` vẫn stale; focused/visual/audit commands dùng `lab\structure_analysis_2\.venv`, còn standard `init.ps1` fallback pass. Đây không phải blocker cho task tiếp theo nhưng cần recreate root venv trước E2E model/UI nếu runtime đó được dùng.

## IMMEDIATE-001 — Chốt contract local cho một PDF_x

**Công việc cần làm**

Định nghĩa chính xác request, result, error và lifecycle cho một lời gọi đồng bộ. Chốt field bắt buộc gồm `input_pdf`, `output_root`, `correlation_id`; chốt output business fields, setting records, warnings, review status, timing, versions và artifact manifest. Quyết định caller Python là interface bắt buộc; local CLI là adapter bắt buộc nếu hệ thống quản lý không chạy Python.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Contract review: phía OCR và phía hệ thống quản lý duyệt request/result/error examples.
- Schema example test: success, success-with-warnings, review-required và failure payload đều đầy đủ.
- Boundary test: contract không chứa Streamlit state, debug-only type hoặc absolute internal temporary path ngoài artifact manifest đã cho phép.
- Single-file scope test: request từ chối folder, nhiều input hoặc PDF_A mode trong giai đoạn immediate.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30 sau khi human xác nhận toàn bộ đề xuất contract. `docs/LOCAL_API_CONTRACT_V1.md` chốt Python là interface chuẩn, JSON serialization và CLI adapter là bắt buộc, một synchronous call chỉ nhận đúng một PDF_x, và ba request fields bắt buộc là `input_pdf`, `output_root`, `correlation_id`. Contract không mở HTTP/network, folder, multiple input hoặc PDF_A mode.
- `contracts/local_api/v1/contract_manifest.json` khóa schema version 1.0, request/result required fields, processing/review/page/confidence enums, stable error codes/stages và boundary policies. Processing `status` (`success`, `success_with_warnings`, `failed`) độc lập với `review_status` (`not_required`, `review_required`); failed result luôn `business=null` và không lộ stack trace.
- Bốn UTF-8 acceptance fixtures (`success`, `success_with_warnings`, `review_required`, `failure`) cung cấp complete request/result examples. Successful fixtures giữ đúng 25 canonical Page-1 fields với value/confidence/resolution/source page; Page-3 setting/note candidates bắt buộc review. Public result không chứa absolute/internal/debug paths; artifact manifest chỉ dùng ID, checksum và relative path dưới request `output_root`.
- Mười sáu focused contract tests pass: interface/single-file decisions, four-scenario coverage, exact Page-1 keys, Unicode round-trip, missing/multiple/folder/PDF_A/unsafe-correlation rejection, status-warning-error invariants, Page-3 review propagation, forbidden debug/stack/absolute path, POSIX/Windows traversal và artifact reference checks. Renderer/CLI content cũng được unit-test bằng tiếng Việt có dấu.
- `scripts/local_api_contract_review.py` validate fixtures trước khi sinh `output/local_api_contract/contract_review.html`; artifact 4.838 bytes hiển thị đủ bốn trạng thái, review safety, counts, error và artifact paths. Automated in-app browser inspection không chạy được vì browser policy chặn `file://`; đây là giới hạn optional visual QA, không chặn renderer/UTF-8/HTML tests và human có thể mở artifact trực tiếp.
- `manual.md` được nối thêm ở cuối từ chương contract, không ghi đè năm chương trước; gồm file map, quy tắc backward-compatible/breaking changes, focused/full test commands và visual CLI. Compileall và `git diff --check` pass; full `init.ps1` pass toàn bộ 148 tests. Root `.venv` vẫn stale nhưng standard fallback và working layout venv xác nhận môi trường đủ cho task contract.

## IMMEDIATE-002 — Tạo package document orchestrator production

**Công việc cần làm**

Tạo `src/relay_form_ocr/` và chuyển orchestration một PDF_x ra khỏi `src/debug_ui`. Service phải tái sử dụng detection, recognition, layout analysis và PDF rendering hiện có; Page 1/Page 2/Page 3+ routing chỉ có một implementation production. Streamlit được sửa để gọi service mới thay vì sở hữu pipeline nghiệp vụ.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test: page-role routing, Page 2 policy, aggregation và warning propagation.
- Integration test: orchestrator dùng fake detector/recognizer nhưng render/layout path thật.
- E2E test: một PDF_x thật sinh result và artifacts đầy đủ.
- Architecture test: `src.relay_form_ocr` không import Streamlit hoặc `src.debug_ui`.
- Regression test: debug UI vẫn xử lý cùng fixture thông qua orchestrator mới.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30 sau khi human xác nhận Page 2 tiếp tục bị bỏ qua có cảnh báo, kết quả giữ dict tương thích Debug UI và `P_003.pdf` là fixture E2E. Package mới gồm `src/relay_form_ocr/__init__.py`, `orchestrator.py` và `visual.py`; public imports ở bước này là `DocumentOcrOrchestrator`, `PdfCandidate`, `ProgressCallback` cùng các helper routing/aggregation. Typed request/result và public `RelayFormOcrService` vẫn được giữ đúng phạm vi IMMEDIATE-003/004.
- `DocumentOcrOrchestrator.extract_pdf_x` là implementation production duy nhất cho render, model lifecycle, Page 1/Page 2/Page 3+ routing, detection, recognition, layout, aggregation, warning propagation, page JSON và relative artifact manifest. VietOCR tiếp tục được khởi tạo trước PaddleOCR và cả hai được tái sử dụng. Page 2 không gọi OCR/layout; Page 3+ warning và note candidate được giữ để review. `important_field_resolution` đưa confidence evidence Page 1 lên kết quả tổng hợp mà không thay đổi các key tương thích trước đó.
- `src/debug_ui/pipeline.py` chỉ còn upload/candidate/PDF_A split concerns và ủy quyền PDF_x extraction cho production orchestrator; không còn routing hoặc aggregation trùng lặp. Architecture test dùng AST xác nhận package production không import Streamlit, `src.debug_ui` hoặc `lab`; regression test xác nhận Debug UI trả nguyên kết quả từ orchestrator.
- `tests.test_document_orchestrator` và `tests.test_debug_ui` pass 13/13: unit routing/Page 2/model order-reuse/aggregation/warning/artifact, integration PDF ba trang dùng Poppler và layout thật với OCR giả, architecture boundary, Debug UI delegation và visual UTF-8. Standard `init.ps1` pass toàn bộ 154 tests; `py_compile` và `git diff --check` pass.
- E2E CPU thật với `data/pdf_split/documents/P_003.pdf` xử lý đủ 8 trang trong 354597.04 ms: 7 trang OCR, 1 Page 2 bỏ qua, 24 Page-1 fields có giá trị, 171 setting records, 1 note candidate và 7 warnings. Manifest có 17 relative artifacts gồm 8 ảnh render, 8 page JSON và `extraction.json`; validation xác nhận đủ tám page artifacts. Lần gọi có progress-to-console kết thúc bằng lỗi encoding `cp1258` sau khi toàn bộ result đã được ghi, nên hướng dẫn E2E chính thức không in callback tiếng Việt; đây không phải lỗi pipeline/artifact.
- Báo cáo HTML tiếng Việt có dấu được sinh từ fixture và kết quả thật tại `output/document_orchestrator/orchestrator_review.html` và `output/document_orchestrator/P_003/orchestrator_review.html`. Renderer test bao phủ ba vai trò trang, cảnh báo và đủ năm mức confidence. `manual.md` được nối thêm file map, ranh giới sửa đổi, focused/full test, visual CLI và E2E command mà không ghi đè các chương trước.

## IMMEDIATE-003 — Tạo typed request/result/error schema

**Công việc cần làm**

Tạo Pydantic models hoặc typed models tương đương cho `OcrRequest`, `OcrResult`, page result, extracted field, setting record, warning, artifact và error. Thêm `schema_version`, `pipeline_version`, `review_status` và JSON serialization ổn định.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Schema unit test: required fields, enums, nullability, numeric bounds và path types.
- Serialization test: model → UTF-8 JSON → model round-trip không mất dữ liệu tiếng Việt.
- Contract fixture test cho success, partial/review-required và error.
- Public payload test: không lộ stack trace, model object hoặc path tạm không thuộc artifact manifest.
- Backward-compatibility fixture cho schema v1.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30 theo bốn quy ước human đã xác nhận: Pydantic v2 (`>=2.10,<3`), `extra="forbid"` trên mọi model, giữ nguyên bốn fixture v1 làm chuẩn backward compatibility và chưa chuyển document orchestrator sang public typed result trước IMMEDIATE-004. Dependency được khai báo tại `src/relay_form_ocr/requirements.txt` và được nối vào full debug/runtime requirements.
- `src/relay_form_ocr/schemas.py` cung cấp immutable `OcrRequest`, `OcrResult` và 14 nested public models cho document, business, đúng 25 Page-1 fields, confidence, setting/note candidate, page, warning, timing/stage timing, artifact manifest và public error. Public exports nằm tại `src.relay_form_ocr/__init__.py`; business/page/warning/artifact/error envelope không dùng `Any`, còn `error.details` chỉ nhận typed JSON values.
- Validation khóa request đúng ba fields, absolute PDF/output paths và safe correlation ID; confidence level/label/score; enum/nullability/numeric bounds; timestamp ordering; Page role/number/policy; success/warning/failure invariants; Page-3 review safety; contiguous successful page coverage; unique/existing artifact references; POSIX relative artifact paths, SHA-256 và size. Public payload từ chối field lạ, traversal, absolute server paths, raw OCR, image/temp/input/output path, model object và traceback/stack keys.
- `schema_export.py` sinh deterministic Draft 2020-12 JSON Schema tại `contracts/local_api/v1/schemas/ocr_request.schema.json` (738 bytes) và `ocr_result.schema.json` (21,085 bytes). Tests so sánh schema đã commit với model output và xác nhận mọi object schema dùng `additionalProperties=false`. `docs/LOCAL_API_CONTRACT_V1.md` đã được cập nhật để trỏ tới models/schema thật.
- Mười chín typed-model tests và mười sáu contract tests pass 35/35: required/extra fields, path type/pattern, exact 25 keys, confidence consistency, immutability, all four fixtures, UTF-8 model→JSON→model round-trip, processing/review/error invariants, Page-3 safety, page coverage, timing, artifact traversal/reference, forbidden debug/stack/absolute paths, schema determinism và visual renderer. `compileall`, `pip check`, `git diff --check` pass; standard `init.ps1` pass toàn bộ 173 tests.
- `schema_visual.py` validate đủ 4/4 fixtures rồi sinh `output/local_api_schema/schema_review.html` (7,046 bytes) bằng tiếng Việt có dấu, hiển thị 16 model public, bốn scenario, 25 Page-1 fields, năm confidence levels và security boundary. In-app browser tiếp tục chặn `file://` theo URL policy nên không có browser screenshot; HTML/UTF-8/scenario content đã được unit-test và artifact sẵn sàng để mở bằng browser desktop.
- `manual.md` được nối thêm, không ghi đè, với public imports, file map, quy tắc non-breaking/breaking, validation/security boundary, schema export, focused/full tests và visual CLI. Runtime mapping sang `OcrResult` thuộc IMMEDIATE-004; workspace/checksum enforcement thuộc IMMEDIATE-006 và exception-specific redaction thuộc IMMEDIATE-007.

## IMMEDIATE-004 — Xây dựng synchronous local Python API

**Công việc cần làm**

Triển khai public service như `RelayFormOcrService.process_pdf(request) -> OcrResult`. Service load/reuse model đúng thứ tự, chỉ xử lý một PDF_x mỗi call, tạo workspace riêng, trả typed result và không yêu cầu Streamlit hoặc cwd cố định.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- API unit test: request validation, service composition và exception-to-error mapping.
- Integration test: caller ngoài package import service và xử lý fixture PDF.
- Model lifecycle test: nhiều call tuần tự tái sử dụng model thay vì load lại mỗi call.
- Working-directory test: gọi service từ cwd khác repository vẫn hoạt động sau khi package được cài/khởi tạo đúng.
- Failure test: PDF không tồn tại, sai extension/signature, PDF rỗng/hỏng, output không ghi được và pipeline stage fail.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30 theo bốn quy ước human đã xác nhận. `src/relay_form_ocr/service.py` cung cấp public `RelayFormOcrService.process_pdf(OcrRequest) -> OcrResult`, giữ một `DocumentOcrOrchestrator` cho toàn vòng đời service và vì vậy tái sử dụng VietOCR/PaddleOCR đúng thứ tự đã khóa. Service xử lý đồng bộ đúng một PDF_x, không import Streamlit/debug/lab và không phụ thuộc cwd khi repository/package đã có trên import path.
- Runtime validation kiểm tra file tồn tại, là file, chữ ký `%PDF-`, cấu trúc có ít nhất một trang, output root và workspace. Workspace tối thiểu là `output_root/<correlation_id>`; workspace có dữ liệu không bị ghi đè. Lỗi runtime dự kiến trả typed `failed` result với message an toàn; raw exception, traceback và absolute internal path không thoát ra public payload. Collision/path hardening đầy đủ vẫn thuộc IMMEDIATE-006, còn granular stage mapping/progress/logging thuộc IMMEDIATE-007.
- Mapper chuyển document identity/SHA-256, đủ 25 Page-1 fields, confidence score/level, Page-3 setting/note candidates, page roles/status, warnings, timing và artifact manifest thành model v1. Page 3+ và Lưu ý luôn `review_required`; Page 2 vẫn `skipped_by_policy` có warning. Mọi public artifact có relative path dưới output root, media type, byte size và SHA-256; page/business references đều trỏ tới artifact thật.
- Mười bốn focused API tests pass: typed mapping/round-trip, success/warning/review, invalid request/file/signature/empty-corrupt PDF/output/collision, safe pipeline failure với partial artifacts, model lifecycle reuse, caller từ external cwd, PDF ba trang với render/layout thật và OCR giả, HTML UTF-8 cùng visual CLI an toàn trên console `cp1258`. Combined service/schema/contract/orchestrator suite pass 56/56; `compileall`, `pip check`, `git diff --check` pass; standard `init.ps1` pass toàn bộ 187 tests.
- Real public-service E2E với `data/pdf_split/documents/P_003.pdf` hoàn tất trong 352939.83 ms: typed result `success_with_warnings/review_required`, 8 trang, 24/25 Page-1 fields có giá trị, 171 setting records, 1 Lưu ý, 7 warnings và 17 artifacts. `OcrResult` validate thành công; audit xác nhận 17/17 artifact tồn tại đúng size/checksum và source SHA-256 khớp. Kết quả nằm tại `output/local_python_api/public_result.json`, workspace `output/local_python_api/immediate-004-p003/`.
- `service_visual.py` sinh `output/local_python_api/service_review.html` bằng tiếng Việt có dấu, gồm trạng thái xử lý/review, ba page roles, warning/error, artifact/timing, security boundary và đủ năm confidence levels. Console summary cố ý dùng ASCII để không lỗi Windows `cp1258`; JSON/HTML vẫn UTF-8. Browser QA qua local HTTP xác nhận report thật render đúng ở viewport 1265×720, không tràn ngang, DOM không lặp và console có 0 warning/error. `manual.md` được nối thêm public imports, model reuse, workspace/error policy, modification boundaries, focused/full tests, visual/E2E và local-report-server commands mà không ghi đè nội dung cũ.

## IMMEDIATE-005 — Tạo local CLI JSON adapter

**Công việc cần làm**

Tạo `python -m src.relay_form_ocr` gọi đúng local Python API, nhận một PDF, xuất result JSON vào stdout hoặc file được chỉ định, ghi log vào stderr và dùng exit code ổn định. Task này là bắt buộc nếu consumer không chạy Python; nếu consumer là Python thì có thể ghi quyết định `not_required` được hai bên xác nhận.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- CLI parser unit test: input/output/correlation options và invalid combinations.
- Subprocess integration test: exit code 0 và stdout là JSON hợp lệ cho success.
- Failure test: exit codes/error JSON ổn định cho invalid PDF, validation error và processing error.
- Stream-separation test: stdout chỉ chứa machine JSON; logs/progress ở stderr.
- Platform test: PowerShell caller đọc JSON và Unicode path/text đúng.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30. `python -m src.relay_form_ocr` nhận đúng `--input`, `--output-root`, `--correlation-id`, optional compatibility `--json`, optional `--output-json` và explicit `--overwrite-result`; mọi request gọi duy nhất `RelayFormOcrService.process_pdf(OcrRequest)`. Đường dẫn tương đối được resolve trước typed boundary; result file có sẵn không bị ghi đè mặc định, còn explicit replacement dùng file tạm và `os.replace`.
- stdout được cô lập ở cả Python stream và native file descriptor trong thời gian tạo/chạy service, vì vậy model/library output đi sang stderr. Không dùng `--output-json` thì stdout có đúng một UTF-8 JSON; dùng file thì stdout rỗng. Public failures giữ nguyên `OcrResult` v1; lỗi trước typed request/adapter dùng `cli_schema_version=1.0` envelope không giả lập correlation ID. Exit code đã khóa: 0 success/warnings, 2 usage/request, 3 input/PDF, 4 output/artifact, 5 processing và 70 internal adapter.
- Mười lăm focused tests pass, gồm parser/invalid combination, validation, invalid/missing PDF, output file/no-overwrite/atomic overwrite, exit mapping, processing/adapter failure, stdout/stderr isolation kể cả buffered output trước crash, subprocess entry point JSON sạch và PowerShell `ConvertFrom-Json` với đường dẫn/thông báo Unicode. Combined CLI/service/schema/contract/orchestrator suite pass 71/71; `compileall`, `pip check`, `git diff --check` pass; standard `init.ps1` pass toàn bộ 202 tests.
- Real CLI E2E với `P_003.pdf` thoát 0 trong 348.3 giây và ghi `output/local_cli_json/public_result.json` trong khi stdout có 0 dòng. Typed result là `success_with_warnings/review_required`, elapsed 345534.95 ms, 8 trang, 24/25 Page-1 fields, 171 setting records, 1 Lưu ý, 7 warnings và 17 artifacts; audit xác nhận 17/17 tồn tại đúng size/checksum và JSON UTF-8 có tiếng Việt.
- `cli_visual.py` sinh report tiếng Việt tại `output/local_cli_json/cli_review.html`, gồm luồng Parse/Validate/Process/Emit, tách stdout/stderr, đủ sáu exit codes và summary E2E. Browser QA local HTTP ở viewport 1265 px xác nhận 4 summary cards, 6 exit rows, không tràn ngang và 0 console warning/error. `docs/LOCAL_API_CONTRACT_V1.md` được bổ sung CLI contract và `manual.md` được nối thêm command, sửa đổi, test, visual/E2E và PowerShell guidance mà không ghi đè nội dung cũ.

## IMMEDIATE-006 — Cô lập workspace và quản lý artifacts cho từng call

**Công việc cần làm**

Mỗi call tạo workspace xác định từ correlation/run ID dưới `output_root`; source PDF chỉ đọc; result trả artifact IDs/relative paths có kiểm soát. Thêm checksum, manifest, collision policy và cleanup thủ công rõ ràng. Không cho output thoát khỏi `output_root`.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test: workspace naming, path resolution, checksum và artifact manifest.
- Security test: `..`, absolute escape, symlink/reparse escape và invalid correlation ID.
- Isolation test: hai call/correlation ID không ghi đè artifacts.
- Source immutability test: hash PDF đầu vào không đổi sau success/failure.
- Unicode/platform test: input/output path tiếng Việt trên Windows.

**Acceptance Evidence**

- `WorkspaceManager` reserve độc quyền `output_root/<correlation_id>`; bất kỳ workspace tồn tại, kể cả rỗng, đều là collision. Marker quản lý trạng thái `active/completed/failed`; artifact path phải là POSIX-relative dưới workspace và output root/workspace/artifact symlink hoặc Windows reparse point đều bị từ chối.
- Success và failure đều finalize `artifact_manifest.json` UTF-8 bằng atomic replace. Manifest vật lý ghi source SHA-256 trước/sau, `source_unchanged`, artifact ID/kind/path/media type/size/checksum và không tự liệt kê; manifest public được thêm vào typed `OcrResult`. Cleanup CLI mặc định dry-run, chỉ xóa đúng marked workspace khi có `--confirm-delete`, không tự retention/quota.
- Mười lăm focused workspace/security/isolation/source/Unicode/cleanup/visual tests và combined workspace/service/CLI/schema/contract/orchestrator suite pass 86/86; `compileall`, `pip check`, `git diff --check` pass; standard `init.ps1` pass toàn bộ 217 tests.
- Real CLI E2E trên `P_003.pdf` với Unicode output root hoàn tất trong 359.4 giây, exit 0 và stdout rỗng ở file mode. Typed result là `success_with_warnings/review_required`: 8 trang, 24/25 Page-1 fields, 171 setting records, 1 Lưu ý, 7 warnings và 18 public artifacts (17 payload artifacts cộng manifest). Audit xác nhận 18/18 public files đúng size/checksum; manifest vật lý có 17 entries, không self-reference; source hash trước/sau cùng là `8b54851d67082d64034ce7b28ef11c8fe9ad0dd9751167e29051a8eca87ab0e8`, marker `completed` và `source_unchanged=true`.
- `workspace_visual.py` sinh report tiếng Việt tại `output/workspace_isolation/workspace_review.html`. Browser QA qua local HTTP ở viewport 1280 px xác nhận đúng 17 dòng manifest, bốn bước lifecycle, trạng thái source “Không thay đổi” và không tràn ngang. `manual.md` được nối thêm hướng dẫn sửa đổi, focused/full test, manifest audit, cleanup dry-run/xác nhận và test trực quan mà không ghi đè nội dung cũ.

## IMMEDIATE-007 — Bổ sung progress, logging và lỗi ổn định cho caller local

**Công việc cần làm**

Cho phép caller truyền progress callback; log theo correlation ID; định nghĩa error codes cho validation, PDF rendering, detection, recognition, layout và filesystem. Không để raw stack trace trở thành public result; vẫn giữ exception chaining/log phục vụ debug.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test: error mapping theo từng stage và `retryable` flag nếu có.
- Callback test: progress tăng đơn điệu, không vượt total và callback exception được xử lý theo policy.
- Logging test: correlation ID có trên mọi stage; không log toàn bộ OCR text/PDF path ngoài policy.
- Failure integration test: injected failure tạo error result/exception public đúng contract và giữ artifacts chẩn đoán phù hợp.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30 theo bốn quy ước human đã xác nhận. Public API là `RelayFormOcrService.process_pdf(request, *, progress=None)` với `ProgressEvent` bất biến, `total=100`, tiến độ tăng đơn điệu, success có đúng một terminal `100/100`, failure kết thúc tại tiến độ thực. Callback exception không làm sai kết quả: callback bị vô hiệu sau lỗi đầu tiên và service ghi `progress_callback_failed`.
- Orchestrator phát event rendering/detection/recognition/layout/artifact nhưng vẫn giữ callback ba đối số tương thích Debug UI. Mười hai `ErrorCode` và bảy `ErrorStage` v1 không đổi; `PipelineStageError` map chính xác validation/rendering/detection/recognition/layout/artifact/pipeline, giữ exception chaining nội bộ và public result không lộ raw message, traceback hay absolute path. Catalog máy đọc được nằm tại `contracts/local_api/v1/error_catalog.json`.
- Structured JSONL logs có timestamp/correlation/stage/event/progress/terminal trên mọi service event. Mặc định không chứa PDF path/tên file, OCR text, exception message hay trace; private debug trace chỉ bật tường minh. CLI đưa service logs sang stderr và giữ stdout machine JSON sạch. Mười một focused observability tests, combined local API/orchestrator suite pass 97/97 và standard `init.ps1` pass toàn bộ 228/228; `compileall`, `pip check` và `git diff --check` pass.
- Real public-service E2E trên `P_003.pdf` hoàn tất trong 334.8 giây với `success_with_warnings/review_required`: 8 trang, 24 Page-1 fields có giá trị, 171 settings, 1 note, 7 warnings và 18 public artifacts đều đúng size/checksum. Trace có 59 events, tăng đơn điệu từ 0 tới 100 và đúng một terminal; 59 JSONL log cùng correlation ID, đủ stage/event và không chứa tên PDF, absolute path, OCR sample hoặc exception trace. Source hash trước/sau giống nhau và manifest không self-reference.
- Báo cáo tiếng Việt có dấu được sinh tại `output/local_observability/observability_review.html`; browser QA ở viewport 1280 px xác nhận 59 dòng progress, đủ 12 error codes, terminal 100/100, log preview đã rút gọn, không `None`, không duplicate DOM và không tràn ngang. `manual.md` được nối thêm hướng dẫn public callback, sửa đổi, test, E2E, replay và visual QA mà không ghi đè nội dung trước.

## IMMEDIATE-008 — Viết consumer example và integration harness

**Công việc cần làm**

Tạo ví dụ nhỏ mô phỏng hệ thống quản lý gọi local API bằng Python và, nếu cần, bằng PowerShell/subprocess. Ví dụ phải nhận một PDF, gọi API, kiểm tra schema/review status và đọc artifact manifest mà không dùng internal implementation details.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Consumer contract test: example chỉ import public symbols.
- E2E test: example xử lý một PDF fixture và đọc được result.
- Review-safety test: example không tự động coi candidate/review-required result là approved data.
- Platform test: chạy từ thư mục consumer riêng trên server Windows.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-30 theo bốn quy ước human đã xác nhận. `examples/local_consumer/python_consumer.py` gọi trực tiếp `RelayFormOcrService` và AST contract test xác nhận project import duy nhất là public `src.relay_form_ocr`; `invoke_ocr.ps1` gọi public CLI. Cả hai chạy từ thư mục consumer Unicode riêng, validate result, đọc physical manifest và kiểm tra relative path/size/SHA-256 mà không dùng orchestrator/workspace/debug/private module.
- Consumer decision gate khóa bốn outcome: `ready_for_use` (exit 0), `manual_review_required` (10), `failed` (20), `consumer_failure` (21); invalid consumer request dùng 2. `review_required`, Page 3+, note hoặc warning không bao giờ thành approved. Manifest/path/checksum/schema sai làm consumer từ chối toàn result. Summary chỉ giữ version/status/review/counts/audit/progress/public code-stage-retryable, không chứa absolute path, OCR text, exception message hay traceback. Python example cô lập Python/native model output khỏi machine stdout.
- Mười một focused consumer tests pass: public-only imports, typed success/failure, physical manifest, review safety, partial artifact failure, tamper, path escape, Python/native stdout isolation, external-cwd Python, external-cwd PowerShell/Unicode và HTML tiếng Việt. Combined consumer/local API/workspace/schema/contract/orchestrator suite pass 108/108; `compileall`, `pip check`, `git diff --check` pass và standard `init.ps1` pass toàn bộ 239/239 tests.
- Real external-cwd E2E trên `P_003.pdf` hoàn tất trong 350.7 giây. Sanitized summary là `success_with_warnings/review_required` và consumer outcome `manual_review_required`: 8 trang, 7 warnings, 18/18 public artifacts verified, physical manifest 17 payload entries, source hash trước/sau giống nhau, 59 progress events, đúng một terminal 100/100 và không có public/consumer error. Independent audit xác nhận 17/17 payload files đúng size/checksum.
- `consumer_visual.py` sinh report tiếng Việt tại `output/local_consumer/consumer_review.html` từ chính E2E summary. Browser QA qua local HTTP ở viewport 1265 px xác nhận năm bước consumer, review gate, 18/18 artifacts, source bất biến, 59 events, không absolute path, không duplicate DOM/tràn ngang và 0 console warning/error. `manual.md` được nối thêm hướng dẫn sửa đổi, Python/PowerShell external-cwd, exit semantics, tests, E2E và visual commands mà không ghi đè nội dung trước.

## IMMEDIATE-009 — Chạy acceptance test với từng PDF thật

**Công việc cần làm**

Chọn một tập nhỏ PDF_x đại diện và chạy từng file qua public local API đúng cách consumer sẽ gọi. Ghi thời gian, warnings, review status, result/artifact locations và lỗi; không tuyên bố accuracy nếu chưa có ground truth.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- E2E test: ít nhất một PDF cho mỗi page-layout family đang hỗ trợ.
- Platform test: cùng server/runtime dự định dùng cho integration.
- Repeatability test: chạy lại cùng PDF/config cho schema/business result ổn định; artifacts không collision.
- Failure E2E test: ít nhất một PDF invalid/hỏng trả lỗi đúng contract.
- Source immutability and artifact audit.

**Acceptance Evidence**

- Ngày 2026-07-31, acceptance runner public-only đã chạy từ thư mục Unicode bên ngoài repository trên CPython 3.12.13/Windows 11 AMD64, CPU, PaddlePaddle 3.3.1 và PyTorch 2.13.0. Revision được khóa ở commit `8f4bebb90a8489b998fe9e5a86b7631554c9bd74`, worktree sạch tại thời điểm chạy, result schema `1.0`, pipeline `0.7.0`.
- Corpus có 8/8 layout families và 8 PDF thật: 7SJ622_1, C264_1, GRL200_1, L90_1, P132_1, P443_1, PCS-902_1 và PCS9611_1. C264_1 được chạy hai lần; thêm một PDF hỏng tạo có kiểm soát để kiểm tra lỗi. Tổng 10/10 executions đạt acceptance, 69 trang thật đã xử lý, 65 warnings và 156 public artifacts.
- Hai lần C264_1 có business-result fingerprint ổn định `1a08f1e3ef248e38054f2058946579a5e15af90bc2ff80b2f04ea280e2468ff2`; mọi workspace tách biệt, không collision. Mọi PDF nguồn giữ nguyên SHA-256 trước/sau; full artifact audit xác minh size/checksum của toàn bộ artifacts. Mọi progress trace thật có đúng một terminal event và kết thúc ở 100/100.
- Failure E2E trả đúng public error `INVALID_PDF`, stage `validation`, `retryable=false`, không tạo business/artifact giả. Tổng thời gian xử lý ghi trong manifest là 3065.1 giây; lệnh runner kết thúc 0 và lệnh verify độc lập với `--full-artifact-audit` cũng kết thúc 0.
- Cả 9 executions thật đều trả `success_with_warnings/review_required`. Đây là bằng chứng review gate hoạt động an toàn, **không phải** bằng chứng độ chính xác OCR vì corpus chưa có ground truth.
- Evidence được lưu tại `output/local_acceptance/immediate-009-cpu-20260731/acceptance_manifest.json`; report tiếng Việt tại `acceptance_review.html`. Browser QA ở 1280 px và 390 px xác nhận đủ 8 family rows, 10 execution rows, không lộ absolute path, không duplicate ID, không tràn trang hoặc console warning/error.
- Verification: 118/118 test kết hợp acceptance/consumer/API/workspace/orchestrator, compileall, `pip check`, `git diff --check` và toàn bộ 249/249 test của `init.ps1` đều pass trước khi chốt tài liệu.

## IMMEDIATE-010 — Cập nhật handoff và khóa phạm vi phiên bản local API v1

**Công việc cần làm**

Cập nhật `README.md`, `ARCHITECTURE.md`, `PROGRESS.md`, `feature_list.json` và file này với public imports/CLI, supported scope, limitations, test commands, acceptance evidence và task tiếp theo. Gắn version local API/schema v1 và quy tắc thay đổi backward-compatible.

**Trạng thái:** Đã hoàn thành.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Documentation command test từ clean checkout/consumer directory.
- Public import/CLI smoke test theo đúng README.
- Link/schema fixture validation.
- Full repository verification: `powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1`.
- Handoff review: Agent tiếp theo xác định được task đã làm, còn thiếu và lệnh tái verification chỉ từ artifacts được cập nhật.

**Acceptance Evidence**

- Hoàn thành ngày 2026-07-31. `contracts/local_api/v1/release_manifest.json` khóa release `ocr_prj.local_api.v1` ở trạng thái `scope_locked`: Local API/schema/CLI `1.0`, pipeline `0.7.0`, implementation commit `8f4bebb90a8489b998fe9e5a86b7631554c9bd74`, acceptance evidence commit `b832edf`; documentation commit được xác định bằng Git HEAD chứa release manifest.
- `README.md` và `ARCHITECTURE.md` từ file rỗng đã trở thành entry point/kiến trúc handoff. `API.md` mới hướng dẫn chi tiết cho team sau khi clone: setup/runtime, source-checkout `PYTHONPATH`, public Python API, model reuse/GPU, progress/log, result/review/error, artifact audit, JSON/CLI/PowerShell consumer, cleanup, contract/schema, tests, compatibility và troubleshooting. Contract, `session-handoff.md` và `manual.md` cũng được cập nhật/nối thêm mà không ghi đè nội dung cũ.
- `scripts/local_api_v1_handoff.py` xác minh version constants, contract, public imports, local Markdown links, deterministic JSON Schema, bốn typed fixtures, documentation, acceptance safety summary và PLAN-001 next-task; đồng thời sinh report HTML tiếng Việt. Tám focused handoff tests pass, gồm public import, CLI help và typed `INPUT_NOT_FOUND`/exit 3 từ external Unicode cwd.
- Combined handoff/contract/models/consumer/acceptance suite pass 64/64; compileall và `pip check` pass. Independent IMMEDIATE-009 evidence verify vẫn đạt 10/10 executions với `--full-artifact-audit`. Full standard `init.ps1` pass 257/257 tests. Local clone sạch của commit `fbade92` chạy lại 8/8 handoff tests, public import/CLI external-cwd và validator thành công, sau đó worktree clone vẫn sạch.
- Report tại `output/local_api_handoff/handoff_review.html` hiển thị version, 8 layout families, 10/10 executions, 69 trang, 156 artifacts, supported scope, limitations, docs và review/accuracy guard bằng tiếng Việt có dấu. Browser QA ở 1280×720 và 390×844 xác nhận responsive, không tràn ngang, duplicate ID, absolute Windows path, `None` hoặc console warning/error.
- Immediate local integration v1 đã hoàn thành nhưng không đồng nghĩa production-ready hay OCR auto-approved. Ground truth/metrics, packaging/deployment, ACL/security, capacity/concurrency và staging/UAT vẫn được giữ đúng trong `plan.md`; task tiếp theo là PLAN-001.

---

## Thứ tự thực hiện bắt buộc

1. IMMEDIATE-001A — Registry schema, loader và append-only merge.
2. IMMEDIATE-001B — Candidate scoring engine và confidence levels.
3. IMMEDIATE-001C — Topology và anchor resolver.
4. IMMEDIATE-001D — Alias, separator và value validators.
5. IMMEDIATE-001E — Page 1 integration và regression evidence.
6. IMMEDIATE-001 — Contract local một PDF.
7. IMMEDIATE-002 — Production orchestrator.
8. IMMEDIATE-003 — Typed schema.
9. IMMEDIATE-004 — Local Python API.
10. IMMEDIATE-005 — CLI adapter nếu consumer không phải Python.
11. IMMEDIATE-006 — Workspace/artifacts.
12. IMMEDIATE-007 — Progress/log/error.
13. IMMEDIATE-008 — Consumer example.
14. IMMEDIATE-009 — Per-PDF acceptance run.
15. IMMEDIATE-010 — Handoff và khóa v1.

Agent phải thực hiện một task tại một thời điểm. Trước khi chuyển task, cập nhật `Trạng thái` và `Acceptance Evidence` của task hiện tại, chạy các test được yêu cầu trong phạm vi task, sau đó cập nhật `PROGRESS.md` và `feature_list.json` theo hướng dẫn repo.

## Definition of Done cho immediate integration

Immediate integration chỉ được coi là hoàn thành khi:

- Caller của hệ thống quản lý gọi được public local Python API hoặc CLI adapter mà không import private/debug modules.
- Mỗi call chỉ nhận đúng một PDF_x và trả typed result/JSON schema v1.
- Input source không bị thay đổi; workspace/artifacts của mỗi call được cô lập.
- Error/progress/review status đủ để consumer xử lý an toàn.
- Per-PDF E2E acceptance runs pass trên server mục tiêu.
- Full repository verification pass và tài liệu/handoff được cập nhật.

Việc immediate integration hoàn thành không đồng nghĩa kết quả OCR được auto-approve. Quyền tự động ghi dữ liệu chính thức vẫn phụ thuộc ground-truth metrics và business acceptance trong `plan.md`.
