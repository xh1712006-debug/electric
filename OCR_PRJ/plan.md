# Kế hoạch hoàn thiện OCR_PRJ thành module OCR tích hợp

Ngày lập kế hoạch: 2026-07-29

## Mục đích

File này chỉ liệt kê **các công việc cần làm tiếp theo** để chương trình hoàn thiện hơn và có thể tích hợp an toàn vào hệ thống quản lý phiếu chỉnh định. Những phần đã làm tốt trong `src/` không được lặp lại thành task để đánh giá lại.

Mặc định mọi task mới có trạng thái **Chưa làm**. Trạng thái chỉ được thay đổi khi có implementation và bằng chứng kiểm chứng tương ứng.

## Quy ước trạng thái

- **Chưa làm**: Chưa bắt đầu implementation của công việc trong task.
- **Đã hoàn thành**: Đã đạt toàn bộ hành vi mục tiêu, tất cả test bắt buộc đã chạy thành công và Acceptance Evidence đã được lưu.
- **Đã làm nhưng chưa được coi là hoàn thành vì một vài lý do nhỏ**: Implementation chính đã có nhưng còn thiếu một phần phạm vi, test, tài liệu, metric hoặc bằng chứng bắt buộc.
- **Đã làm nhưng lỗi**: Implementation đã có nhưng hành vi mục tiêu sai, có regression, test bắt buộc fail hoặc không đạt ngưỡng chấp nhận.

## Quy tắc Acceptance Evidence chung

Mỗi task phải lưu bằng chứng có thể kiểm tra lại, tối thiểu gồm:

- Commit/build hoặc danh sách file implementation.
- Lệnh test đã chạy, ngày chạy và kết quả pass/fail.
- Artifact đặc thù của task như report metric, JSON Schema, local API integration log, ảnh review hoặc biên bản UAT.
- Lý do cụ thể nếu task chỉ được đánh dấu hoàn thành một phần hoặc bị lỗi.

Không dùng câu “đã test thủ công” làm bằng chứng duy nhất. Không coi việc unit test pass là bằng chứng đủ cho độ chính xác OCR nghiệp vụ, khả năng chạy trên platform production hoặc khả năng tích hợp E2E.

---

## PLAN-001 — Chốt phạm vi nghiệp vụ và ranh giới tích hợp

**Công việc cần làm**

Thống nhất với phía hệ thống quản lý phiếu về input chính thức, output cần nhận, các field bắt buộc, loại phiếu/template được hỗ trợ, trách nhiệm review, điều kiện ghi dữ liệu vào hệ thống chính và chính sách đối với Page 2, Table 02, phần “Lưu ý”. Ghi các quyết định thành tài liệu product contract/ADR.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Requirements review: đại diện nghiệp vụ và kỹ thuật duyệt danh sách input/output và supported templates.
- Schema example test: ít nhất một payload mẫu cho success, partial result, review required và failure.
- Traceability test: mỗi field public được ánh xạ tới nguồn trang/section và consumer trong hệ thống quản lý.
- Boundary test: xác định rõ dữ liệu nào OCR chịu trách nhiệm và dữ liệu nào hệ thống quản lý chịu trách nhiệm.

**Acceptance Evidence**

- Hiện chưa có product/integration contract cấp repo được phê duyệt, nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu tài liệu đã duyệt, danh sách người duyệt, ngày duyệt, payload mẫu và bảng traceability.
- Nếu còn quyết định mở ảnh hưởng schema/API thì chỉ được đánh dấu hoàn thành một phần.
- Nếu tài liệu mâu thuẫn với output thực tế hoặc consumer không chấp nhận payload mẫu thì đánh dấu Đã làm nhưng lỗi.

## PLAN-002 — Xây dựng ground-truth dataset đại diện

**Công việc cần làm**

Chọn tập phiếu đại diện theo loại relay, template, chất lượng scan và nguồn tài liệu. Gán nhãn ranh giới PDF_A, text OCR, Page 1 fields, Page 3+ records và phần “Lưu ý”. Chia train/validation/test theo tài liệu hoặc template để tránh rò rỉ dữ liệu giữa các tập.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Dataset validation test: kiểm tra schema annotation, ID trùng, bbox không hợp lệ, field bắt buộc và file ảnh/PDF bị thiếu.
- Leakage test: cùng một document/template family không xuất hiện sai quy tắc ở cả train và held-out test.
- Inter-annotator test: hai người gán nhãn độc lập trên một tập overlap và đo mức đồng thuận.
- Privacy test: dữ liệu dùng cho test/training có quyền sử dụng và chính sách bảo quản rõ ràng.

**Acceptance Evidence**

- Hiện chưa có labeled ground truth đủ để đo chất lượng, nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu dataset manifest có version, annotation guide, validation report, split manifest và báo cáo inter-annotator agreement.
- Thiếu một section annotation hoặc chưa có held-out test set thì chỉ hoàn thành một phần.
- Validation fail, leakage hoặc nhãn không nhất quán vượt ngưỡng cho phép thì đánh dấu Đã làm nhưng lỗi.

## PLAN-003 — Thiết lập bộ metric và quality gates nghiệp vụ

**Công việc cần làm**

Định nghĩa và đo splitter accuracy, CER/WER, Page 1 field exact match, Page 3 record/field precision-recall-F1, tỷ lệ cảnh báo, tỷ lệ cần review và tỷ lệ lỗi âm thầm. Chốt ngưỡng chấp nhận với nghiệp vụ.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Evaluation unit test: metric trả đúng kết quả trên fixture nhỏ đã biết đáp án.
- Baseline evaluation: chạy toàn bộ held-out test set và sinh report theo document/template.
- Regression test: fail khi metric giảm vượt tolerance đã cấu hình.
- Business acceptance test: ngưỡng tự động chấp nhận, cần review và từ chối được phê duyệt.

**Acceptance Evidence**

- Hiện chưa có metric report chính thức nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu script evaluation, baseline report, ngưỡng đã duyệt và lệnh tái chạy.
- Có report nhưng chưa chốt ngưỡng hoặc chưa bao phủ một output nghiệp vụ thì chỉ hoàn thành một phần.
- Metric tính sai, không tái lập được hoặc thấp hơn ngưỡng đã duyệt thì đánh dấu Đã làm nhưng lỗi.

## PLAN-004 — Hoàn thiện trích xuất Table 02 của Page 1

**Công việc cần làm**

Thiết kế schema và extractor cho Table 02 đang bị bỏ qua. Nếu nghiệp vụ xác nhận không cần Table 02, thay implementation bằng policy `not_applicable` có lý do và quyết định chính thức, thay vì chỉ skip tạm thời.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test: merged cells, multiline text, bảng thiếu đường kẻ, bảng có số hàng biến đổi và OCR block cắt qua nhiều cell.
- Schema contract test: record/field của Table 02 đúng type, nullability và evidence.
- E2E test: PDF → OCR → Page 1 result có Table 02 trên các template được hỗ trợ.
- Accuracy test: record/field precision-recall-F1 trên ground truth.
- Business acceptance test: dữ liệu trích xuất đúng ý nghĩa nghiệp vụ.

**Acceptance Evidence**

- Công việc mới chưa bắt đầu; việc skip hiện tại không phải bằng chứng hoàn thành.
- Để hoàn thành: lưu extractor hoặc ADR `not_applicable`, test report, accuracy report và ảnh/evidence review mẫu.
- Extractor đã có nhưng thiếu metric hoặc còn template trong phạm vi chưa hỗ trợ thì hoàn thành một phần.
- Gán sai record/cell, làm hỏng Page 1 hiện có hoặc metric dưới ngưỡng thì đánh dấu Đã làm nhưng lỗi.

## PLAN-005 — Hoàn thiện xử lý Page 2 và phần “Lưu ý”

**Công việc cần làm**

Chuyển policy Page 2 và raw “Lưu ý” thành hành vi document-level chính thức: xác định khi nào Page 2 được bỏ qua, khi nào phải cảnh báo; trích xuất ranh giới/nội dung “Lưu ý”, evidence và schema mà consumer cần.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test: heading có/không dấu, heading bị tách OCR block, nội dung nhiều dòng/nhiều trang và không có heading.
- Policy test: Page 2 đúng template được `not_applicable`; Page 2 bất thường tạo warning thay vì bị bỏ qua âm thầm.
- E2E test: PDF_x hoàn chỉnh trả đúng page roles và nội dung Lưu ý.
- Accuracy test: section-boundary F1 và text CER trên ground truth.
- Business acceptance test: consumer xác nhận raw text hay structured fields phù hợp nhu cầu.

**Acceptance Evidence**

- Task mới chưa bắt đầu; raw candidate trong debug UI không được tính là implementation production hoàn chỉnh.
- Để hoàn thành: lưu policy, schema, E2E fixtures, metric report và review nghiệp vụ.
- Chỉ xử lý được một template hoặc chưa có document-level aggregation thì hoàn thành một phần.
- Nuốt nhầm setting records, bỏ mất Lưu ý hoặc skip Page 2 bất thường không cảnh báo thì đánh dấu Đã làm nhưng lỗi.

## PLAN-006 — Nâng độ tin cậy của Page 3+ setting records

**Công việc cần làm**

Dùng ground truth để sửa các trường hợp record grouping còn yếu: cột dịch chuyển, block merge/split, bảng không có đường kẻ, value nhiều dòng, nhiều table region và unit/description không rõ. Bổ sung confidence/calibration để quyết định auto-accept hay review.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test cho từng failure family đã phát hiện từ ground truth.
- Integration test: OCR regions thật đi qua table-grid và reconstruction.
- Accuracy test: record precision/recall và field F1 theo từng template.
- Calibration test: confidence bucket phản ánh xác suất đúng thực tế.
- Negative test: metadata/header không trở thành setting record.

**Acceptance Evidence**

- Đây là công việc cải thiện mới dựa trên ground truth; hiện chưa bắt đầu.
- Để hoàn thành: lưu danh sách failure families, regression fixtures, before/after metric report và calibration report.
- Metric tổng tăng nhưng còn family trong phạm vi chưa được test thì hoàn thành một phần.
- Regression trên template cũ hoặc tạo record sai không có warning thì đánh dấu Đã làm nhưng lỗi.

## PLAN-007 — Tạo document-level production orchestrator độc lập với UI

**Công việc cần làm**

Tạo package production, ví dụ `src/relay_form_ocr/`, sở hữu luồng PDF_x → render → detection → recognition → page-role analysis → document result. Streamlit, local Python API và CLI adapter phải gọi cùng service này; `debug_ui` chỉ còn trách nhiệm hiển thị.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test: page-role routing, aggregation, warning propagation và lỗi từng stage.
- Integration test: orchestrator với fake detector/recognizer nhưng PDF rendering/layout thật.
- E2E test: một PDF_x thật sinh document result và artifacts đầy đủ.
- Architecture test: production orchestrator không import Streamlit hoặc `src.debug_ui`.
- Idempotency/workspace test: hai document/job không ghi đè artifacts của nhau.

**Acceptance Evidence**

- Task mới chưa bắt đầu; orchestration hiện có trong debug UI chỉ là baseline để tái sử dụng khi triển khai.
- Để hoàn thành: lưu public service interface, architecture test và E2E artifact manifest.
- Service đã tách nhưng UI vẫn chứa logic nghiệp vụ trùng lặp hoặc local API phải gọi debug package thì hoàn thành một phần.
- Kết quả khác với pipeline hiện tại không có migration/giải thích hoặc trộn workspace giữa job thì đánh dấu Đã làm nhưng lỗi.

## PLAN-008 — Định nghĩa stable result contract và error contract v1

**Công việc cần làm**

Tạo Pydantic models và JSON Schema cho document, page, extracted field, setting record, warning, review status, artifact và error. Phân biệt business result với raw evidence; loại absolute server path khỏi public payload; định nghĩa versioning/backward compatibility.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Schema unit test: required fields, enum, nullability, numeric bounds và cross-field rules.
- Contract test: mọi fixture success/partial/failure validate theo schema v1.
- Serialization test: UTF-8 round-trip và payload size giới hạn hợp lý.
- Backward-compatibility test: thay đổi non-breaking không làm fixture v1 cũ mất hiệu lực.
- Security payload test: không có absolute path, secret hoặc internal stack trace.

**Acceptance Evidence**

- Stable public contract mới chưa được tạo nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu Pydantic models, exported JSON Schema, fixtures và contract test report.
- Schema đã có nhưng chưa bao phủ partial/error hoặc chưa được consumer review thì hoàn thành một phần.
- Output runtime không validate hoặc thay đổi phá vỡ v1 không tăng version thì đánh dấu Đã làm nhưng lỗi.

## PLAN-009 — Chuẩn hóa package, dependencies và model provenance

**Công việc cần làm**

Tạo `pyproject.toml`, dependency lock cho deployment, Python/platform support matrix, model manifest/checksum, quy trình cache/offline model và cấu hình runtime theo environment.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Packaging test: build wheel/sdist và cài vào clean environment.
- Import test: public package hoạt động không phụ thuộc repository working directory.
- Dependency test: locked install và `pip check` pass.
- Model provenance test: checksum/version đúng; model bundle giả mạo bị từ chối.
- Offline/platform test: khởi tạo runtime trên platform được hỗ trợ không cần tải bất ngờ.

**Acceptance Evidence**

- Công việc chuẩn hóa package/deployment mới chưa bắt đầu; script local hiện tại là baseline chứ chưa phải artifact triển khai.
- Để hoàn thành: lưu package artifact, lock file, support matrix, model manifest và clean-install logs.
- Package cài được nhưng model vẫn phụ thuộc tải không kiểm soát hoặc thiếu platform target thì hoàn thành một phần.
- Clean install/import/model warm-up fail thì đánh dấu Đã làm nhưng lỗi.

## PLAN-010 — Xây dựng local application API v1

**Công việc cần làm**

Tạo public Python API để hệ thống quản lý chạy trên cùng server gọi trực tiếp một PDF hoặc document request và nhận typed result. Nếu consumer không dùng Python, cung cấp local CLI/subprocess adapter trao đổi JSON. Không mở HTTP port và không yêu cầu network transport.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- API unit test: request validation, service composition và error mapping.
- Contract test: public request/result models khớp JSON Schema v1.
- Python integration test: consumer chỉ import public symbols và xử lý được một PDF.
- CLI/subprocess integration test nếu consumer không dùng Python: exit code và stdout JSON ổn định.
- E2E test: caller trong thư mục/process của hệ thống quản lý gửi đường dẫn PDF local và nhận kết quả hợp lệ.
- Failure test: PDF không tồn tại/hỏng/quá giới hạn, output không ghi được và pipeline failure.
- Platform test: gọi local API trên đúng server/runtime production, kể cả đường dẫn Unicode.

**Acceptance Evidence**

- Local application API chưa tồn tại nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu public imports/signatures, JSON Schema, consumer example, E2E report và lệnh gọi local.
- Python API chạy nhưng còn phụ thuộc Streamlit/private modules, result không theo contract hoặc chưa có adapter cần thiết cho consumer thì hoàn thành một phần.
- API ghi đè source/artifacts, hỏng contract, lộ internal stack/path ngoài policy hoặc caller không xử lý được lỗi thì đánh dấu Đã làm nhưng lỗi.

## PLAN-011 — Bổ sung local job runner và persistence khi cần xử lý nền

**Công việc cần làm**

Khi synchronous local API không còn đủ vì thời gian OCR hoặc số lượng yêu cầu tăng, bổ sung local job runner trên cùng máy. Lưu job state bằng SQLite hoặc store local phù hợp; hỗ trợ queued/running/completed/failed/cancelled, idempotency, retry và phục hồi sau restart. Không sử dụng network queue nếu chưa có nhu cầu thực tế.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- State-machine unit test cho mọi transition hợp lệ/không hợp lệ.
- Integration test: local caller enqueue, runner claim và complete/fail job.
- Restart recovery test: restart runner/process/store giữa job không làm mất hoặc chạy trùng ngoài policy.
- Idempotency test: retry cùng key trả cùng logical job.
- Retry test: phân biệt lỗi retryable và non-retryable.
- Concurrency test: các local runner không cùng claim một job; hoặc single-runner lock chặn process thứ hai đúng policy.

**Acceptance Evidence**

- Local job infrastructure mới chưa được triển khai nên task ở trạng thái Chưa làm. Task có thể được hoãn nếu synchronous one-PDF call vẫn đáp ứng SLO đã duyệt.
- Để hoàn thành: lưu state diagram, SQLite/store migration, runner logs và restart/idempotency/concurrency test report.
- Happy path chạy nhưng chưa phục hồi restart hoặc chưa có idempotency thì hoàn thành một phần.
- Mất job, double processing ngoài policy hoặc transition sai thì đánh dấu Đã làm nhưng lỗi.

## PLAN-012 — Xây dựng document/artifact storage an toàn

**Công việc cần làm**

Tạo local storage abstraction cho source PDF, split PDFs, rendered images, raw OCR, result và review evidence. Public local API dùng artifact ID hoặc relative path dưới một output root đã kiểm soát; có retention, checksum, cleanup và quota. Không cần object storage hoặc download URL.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Unit test: artifact metadata, naming, ownership, checksum và retention rules.
- Integration test: đọc source/write artifacts theo local contract, byte hash source không đổi.
- Security test: path traversal, output-root escape, symlink/reparse escape và truy cập workspace không thuộc correlation/run ID.
- Cleanup test: xóa đúng artifacts hết hạn, không xóa nhầm dữ liệu job khác.
- Large-file/platform test: file lớn được đọc theo cách có giới hạn RAM và hoạt động trên local filesystem target.

**Acceptance Evidence**

- Storage layer mới chưa tồn tại nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu storage interface/adapter, cấu hình output root, security/cleanup report và public payload audit.
- Lưu được file nhưng chưa có retention/quota hoặc path contract chưa ổn định thì hoàn thành một phần.
- Mất dữ liệu, hash sai, path escape hoặc ghi đè workspace khác thì đánh dấu Đã làm nhưng lỗi.

## PLAN-013 — Bổ sung local trust boundary và input security

**Công việc cần làm**

Xác định process/user nào trên server được phép gọi OCR và đọc artifacts. Kiểm soát input/output roots, file ownership/ACL, PDF validation, malware-scan boundary, file/page/resource limits, secret/config management và audit trail. Không xây token/OAuth/network authentication khi không có HTTP transport.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Process/ACL test: service account được phép đọc input/write output; user ngoài policy bị hệ điều hành từ chối.
- Path-scope test: input ngoài allowed roots và output-root escape bị chặn theo policy.
- Input security test: giả PDF, polyglot, path traversal, file quá lớn, quá nhiều trang và encrypted PDF.
- Resource-limit/quota test cho từng local call/process.
- Secret/dependency scan trong CI.
- Audit test: process call/read/cleanup đều ghi actor hoặc service identity, timestamp và correlation ID.

**Acceptance Evidence**

- Local trust/security layer mới chưa được triển khai nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu local threat model/checklist, service-account/ACL configuration, input-security report và audit log mẫu đã khử dữ liệu nhạy cảm.
- Có path validation nhưng thiếu ACL, resource limits, scan boundary hoặc audit thì hoàn thành một phần.
- Process ngoài policy đọc được dữ liệu, path escape, secret leakage hoặc bypass input validation thì đánh dấu Đã làm nhưng lỗi và chặn release.

## PLAN-014 — Xây dựng human review và correction history

**Công việc cần làm**

Cho phép người nghiệp vụ đối chiếu ảnh/evidence, sửa field/record, ghi người sửa/thời gian/lý do, giữ raw OCR bất biến và approve/reject/lock kết quả trước khi hệ thống quản lý sử dụng.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Workflow unit test: pending_review, accepted, corrected, rejected và locked.
- Authorization test: chỉ đúng role được sửa/approve/lock.
- Revision test: correction tạo revision mới; raw OCR/evidence gốc không bị ghi đè.
- Conflict test: hai reviewer sửa đồng thời được phát hiện/giải quyết.
- E2E test: OCR → review → correction → approve → consumer nhận approved result.
- Business UAT với người dùng thật.

**Acceptance Evidence**

- Review workflow mới chưa tồn tại nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu state model, revision/audit fixtures, E2E recording/report và biên bản UAT.
- Chỉ xem được evidence nhưng chưa lưu correction/approval history thì hoàn thành một phần.
- Mất raw result, sửa không có audit hoặc consumer nhận candidate chưa duyệt trái policy thì đánh dấu Đã làm nhưng lỗi.

## PLAN-015 — Bổ sung logging, metrics, runtime checks và alerting

**Công việc cần làm**

Thêm structured logs theo correlation/run/document ID, stable error taxonomy, local runtime self-check, metrics theo từng pipeline stage và cảnh báo phù hợp cho model/storage/resource failures. Nếu chưa có background runner thì không cần network health endpoint.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Logging unit test: log có correlation fields và không chứa secret/raw sensitive text ngoài policy.
- Error mapping test: exception nội bộ thành stable public error code.
- Runtime-check test: self-check fail khi model, Poppler hoặc storage chưa sẵn sàng.
- Metrics integration test: call count, failure, latency, pages và RAM/VRAM được ghi; thêm queue depth nếu PLAN-011 được triển khai.
- Operational drill: model load fail, disk full, stuck call và local runner crash tạo log/cảnh báo đúng.

**Acceptance Evidence**

- Observability layer mới chưa được triển khai nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu log mẫu, error catalog, metrics/dashboard snapshot và operational-drill report.
- Có log nhưng thiếu correlation/runtime-check/alert hoặc lộ dữ liệu nhạy cảm thì hoàn thành một phần hoặc lỗi tùy mức độ.
- Không phát hiện failure quan trọng hoặc public response lộ stack/path thì đánh dấu Đã làm nhưng lỗi.

## PLAN-016 — Kiểm thử hiệu năng, concurrency và resource limits

**Công việc cần làm**

Đo và tối ưu thời gian/call, thời gian/trang, RAM/VRAM và model reuse trên phần cứng production. Xác định timeout, max pages/file và quy tắc serialize/concurrency cho các local callers; chỉ đo queue throughput nếu PLAN-011 được triển khai.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Benchmark test trên corpus có kích thước/loại tài liệu đại diện.
- Load test: nhiều local caller/process với concurrency tăng dần hoặc xác nhận single-call lock hoạt động đúng.
- Soak test: chạy kéo dài để phát hiện memory leak và model/resource degradation.
- Resource-limit test: file/page/call vượt ngưỡng bị từ chối có kiểm soát.
- GPU/CPU platform test theo deployment matrix.
- Cancellation/timeout test: process/runner giải phóng resource đúng.

**Acceptance Evidence**

- Performance plan mới chưa được thực hiện nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu hardware spec, benchmark/load/soak reports và approved capacity configuration.
- Chỉ có benchmark đơn lẻ nhưng chưa có concurrency/soak hoặc chưa chốt SLO thì hoàn thành một phần.
- OOM, deadlock, model load lặp không kiểm soát hoặc SLO dưới ngưỡng thì đánh dấu Đã làm nhưng lỗi.

## PLAN-017 — Thiết lập CI quality gates

**Công việc cần làm**

Tự động chạy format/lint, type-check, unit, integration, contract, security scan và regression metrics phù hợp. Các E2E/model tests nặng có thể chạy scheduled hoặc trên release candidate nhưng phải có gate rõ ràng.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- CI matrix cho Python/platform được hỗ trợ.
- Lint/format/type-check gates cho production code.
- Unit/integration tests với coverage report và threshold.
- Contract compatibility, secret scan và dependency vulnerability scan.
- Scheduled E2E/accuracy regression trên versioned test corpus.
- Clean-checkout test: pipeline không phụ thuộc artifact local chưa track.

**Acceptance Evidence**

- CI quality gates mới chưa được thiết lập nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu workflow/config, một CI run xanh từ clean checkout và toàn bộ report artifacts.
- Chỉ chạy unit test nhưng thiếu type/security/contract/accuracy gate thì hoàn thành một phần.
- CI xanh sai do skip test bắt buộc, dùng cache cũ hoặc không tái lập được local thì đánh dấu Đã làm nhưng lỗi.

## PLAN-018 — Đóng gói và triển khai local runtime reproducible

**Công việc cần làm**

Đóng gói Python package/runtime để hệ thống quản lý trên cùng server có thể import local API hoặc gọi CLI ổn định. Chuẩn bị model, Poppler, environment config, upgrade/rollback và runbook. Chỉ cần Windows service/background runner nếu PLAN-011 được triển khai; không cần web server hoặc mở port.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Build test: tạo deployment artifact từ clean checkout.
- Smoke test: public Python import hoặc CLI, local storage và model self-check hoạt động sau deploy.
- E2E test từ process/thư mục của hệ thống quản lý trên environment giống production.
- Upgrade/rollback test không làm hỏng contract hoặc mất artifacts; thêm restart/job recovery nếu PLAN-011 có trong scope.
- Platform test cho CPU/GPU, Poppler, Unicode path và local filesystem target.
- Recovery test cho SQLite/job metadata nếu PLAN-011 có trong scope.

**Acceptance Evidence**

- Deployment artifact chính thức mới chưa tồn tại nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu image/package version, deployment manifest, smoke/E2E/rollback report và runbook drill.
- Deploy được thủ công nhưng không reproducible hoặc chưa có rollback/backup evidence thì hoàn thành một phần.
- Clean deploy/import/CLI fail, mất dữ liệu khi upgrade hoặc runtime self-check báo sai thì đánh dấu Đã làm nhưng lỗi.

## PLAN-019 — Hoàn thiện tài liệu sản phẩm, local API và vận hành

**Công việc cần làm**

Viết tài liệu cấp repo về mục tiêu module, kiến trúc, data flow, supported templates, limitations, setup, public Python API/CLI examples, schema/versioning, local deployment, security, operations và troubleshooting.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Documentation command test: lệnh setup/import/CLI chạy được từ clean checkout và consumer directory.
- Link/schema test: internal links và JSON Schema references hợp lệ.
- New-developer test: người chưa tham gia dự án setup và chạy smoke test chỉ từ tài liệu.
- Runbook drill: xử lý model load failure, stuck job, disk full, rollback và credential rotation theo hướng dẫn.
- Architecture review: sơ đồ và mô tả khớp implementation thực tế.

**Acceptance Evidence**

- Tài liệu cấp repo cần thiết chưa được viết nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu README/architecture/local-API/runbook, clean-machine walkthrough và reviewer approval.
- Tài liệu có nhưng lệnh không chạy, thiếu limitations/runbook hoặc lệch code thì hoàn thành một phần.
- Người mới không thể chạy theo hướng dẫn hoặc runbook drill thất bại vì hướng dẫn sai thì đánh dấu Đã làm nhưng lỗi.

## PLAN-020 — Tích hợp staging và UAT với hệ thống quản lý phiếu

**Công việc cần làm**

Tạo adapter staging trong hệ thống quản lý để gọi public Python API hoặc local CLI trên cùng server, nhận result, xử lý lỗi/retry local và map contract OCR sang domain của hệ thống quản lý. Nếu PLAN-011 được dùng thì theo dõi local job; nếu không thì xử lý synchronous result. Chạy UAT trước production rollout.

**Trạng thái:** Chưa làm.

**Các test cụ thể cần có để coi là đã hoàn thành**

- Consumer contract test giữa OCR local API/CLI và management-system adapter.
- Mapping unit test: field, unit, null, warning, review status và revisions không bị mất.
- Local-process resilience test: timeout, retry, duplicated call, process crash và filesystem/model unavailable.
- Staging E2E test: local call → OCR → review → approve → dữ liệu xuất hiện đúng trong hệ thống quản lý.
- Security/platform test cho service account, ACL và runtime trên cùng server.
- Business UAT và rollback rehearsal.

**Acceptance Evidence**

- Tích hợp staging mới chưa bắt đầu nên task ở trạng thái Chưa làm.
- Để hoàn thành: lưu contract-test report, sanitized local-call traces, mapping report, UAT sign-off và rollback rehearsal.
- Chỉ happy path hoạt động nhưng chưa có retry/idempotency/review hoặc UAT thì hoàn thành một phần.
- Mapping sai, tạo bản ghi trùng, nhận candidate chưa duyệt trái policy hoặc không rollback được thì đánh dấu Đã làm nhưng lỗi.

---

## Thứ tự thực hiện khuyến nghị

### Giai đoạn 1 — Chốt đúng sản phẩm và đo được chất lượng

1. PLAN-001 — Phạm vi nghiệp vụ và ranh giới tích hợp.
2. PLAN-002 — Ground-truth dataset.
3. PLAN-003 — Metrics và quality gates.

### Giai đoạn 2 — Hoàn thiện dữ liệu OCR nghiệp vụ

4. PLAN-004 — Table 02.
5. PLAN-005 — Page 2 và Lưu ý.
6. PLAN-006 — Page 3+ setting records.

### Giai đoạn 3 — Tạo lõi tích hợp ổn định

7. PLAN-007 — Document orchestrator.
8. PLAN-008 — Result/error contract v1.
9. PLAN-009 — Package, dependency và model provenance.

### Giai đoạn 4 — Xây local integration dùng được trên cùng server

10. PLAN-010 — Local application API.
11. PLAN-011 — Local jobs và persistence nếu cần xử lý nền.
12. PLAN-012 — Local artifact storage.
13. PLAN-013 — Local trust boundary và input security.
14. PLAN-014 — Human review.

### Giai đoạn 5 — Production hardening và rollout

15. PLAN-015 — Observability.
16. PLAN-016 — Performance/concurrency.
17. PLAN-017 — CI quality gates.
18. PLAN-018 — Deployment.
19. PLAN-019 — Documentation.
20. PLAN-020 — Staging integration và UAT.

## Điều kiện trước khi cho hệ thống ngoài sử dụng production

Không được coi module là production-ready chỉ vì local API gọi được. Tối thiểu PLAN-001, PLAN-002, PLAN-003, PLAN-007, PLAN-008, PLAN-010, PLAN-012, PLAN-013, PLAN-015, PLAN-016, PLAN-018 và PLAN-020 phải ở trạng thái **Đã hoàn thành**. PLAN-011 chỉ bắt buộc nếu hệ thống cần xử lý nền, phục hồi job hoặc nhiều request cạnh tranh. Các task trích xuất PLAN-004–PLAN-006 phải hoàn thành hoặc có quyết định nghiệp vụ chính thức loại chúng khỏi phạm vi hỗ trợ.
