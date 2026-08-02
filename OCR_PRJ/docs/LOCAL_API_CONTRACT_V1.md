# Local application contract v1 cho một PDF_x

Trạng thái: đã chốt cho IMMEDIATE-001 ngày 2026-07-30, được triển khai bằng
`RelayFormOcrService` trong IMMEDIATE-004 và được khóa phạm vi handoff tại
IMMEDIATE-010. Local API/schema/CLI đều là `1.0`; pipeline implementation hiện là
`0.7.0`. Machine-readable release state nằm tại
[`release_manifest.json`](../contracts/local_api/v1/release_manifest.json).

## Quyết định interface

- Interface chuẩn là Python: `RelayFormOcrService.process_pdf(request)`.
- JSON là dạng serialization bắt buộc của request/result.
- CLI JSON vẫn là adapter bắt buộc ở IMMEDIATE-005 để không phụ thuộc runtime
  của hệ thống quản lý.
- Mỗi lời gọi chạy đồng bộ và chỉ nhận đúng một PDF_x. Folder, danh sách file,
  PDF_A và network/HTTP đều ngoài phạm vi v1.
- Lời gọi chỉ trả một terminal result sau success hoặc failure. Caller có thể truyền
  callback tùy chọn qua `process_pdf(request, *, progress=...)`; callback chỉ quan sát
  tiến độ và không thay đổi terminal result.

Machine-readable decision catalog nằm tại
`contracts/local_api/v1/contract_manifest.json`. Typed Pydantic v2 models chính thức
nằm trong `src/relay_form_ocr/schemas.py`; JSON Schema được export tại
`contracts/local_api/v1/schemas/ocr_request.schema.json` và
`contracts/local_api/v1/schemas/ocr_result.schema.json`.

## Request v1

Ba field đều bắt buộc và không nhận field lạ trong v1:

| Field | Kiểu public | Quy tắc |
|---|---|---|
| `input_pdf` | `Path`/JSON string | Đường dẫn tuyệt đối tới đúng một file `.pdf`; caller cam kết đây là PDF_x. |
| `output_root` | `Path`/JSON string | Đường dẫn tuyệt đối tới root artifacts mà process được phép ghi. |
| `correlation_id` | string | 1–128 ký tự ASCII, bắt đầu bằng chữ/số, sau đó chỉ gồm chữ/số, `.`, `_`, `-`. |

Request không nhận `input_mode`, `folder_dir`, `input_pdfs` hoặc PDF bytes.
Validation/runtime ở IMMEDIATE-004 phải từ chối directory, file không tồn tại,
file không phải PDF và input được nhận diện là PDF_A bằng error code ổn định.

## Result envelope v1

Mọi terminal result có cùng top-level fields:

- `schema_version`: cố định `1.0` cho contract này.
- `pipeline_version`: version implementation thực thi request.
- `correlation_id`: đúng ID của request.
- `status`: `success`, `success_with_warnings` hoặc `failed`.
- `review_status`: `not_required` hoặc `review_required`.
- `document`: identity không chứa source path; gồm ID, tên file, SHA-256 và số
  trang. Giá trị là `null` nếu validation thất bại trước khi nhận diện document.
- `business`: Page 1 fields, Page 3+ setting candidates và note candidates;
  phải là `null` khi `status=failed`.
- `pages`: trạng thái/role từng trang nhưng không nhúng raw OCR hoặc debug object.
- `warnings`: danh sách warning có code/message/stage và optional page number.
- `timing`: UTC started/completed time, tổng milliseconds và stage timings.
- `artifact_manifest`: workspace ID và artifacts bằng relative path.
- `error`: `null` khi thành công; object ổn định khi thất bại.

`status` mô tả kết quả xử lý, còn `review_status` mô tả khả năng sử dụng dữ
liệu. Hai trạng thái độc lập: một request có thể xử lý thành công nhưng vẫn cần
review vì có Page 3+ candidate hoặc field confidence không đủ.

## Business result

`business.page1_fields` luôn có đủ 25 canonical Page 1 keys khi Page 1 đã được
xử lý. Mỗi field có:

- `value`: string hoặc `null`.
- `confidence`: `null` hoặc `{level: 1..5, label, score: 0..100}`.
- `resolution_status`: `auto_selected`, `preserved_existing`,
  `review_required` hoặc `not_available`.
- `source_page`: trang nguồn hoặc `null`.

Score breakdown, OCR polygons và raw field-resolution evidence được lưu trong
artifact, liên kết qua `business.evidence_artifact_ids`; không nhúng toàn bộ
vào business payload.

Mọi `setting_records` Page 3+ phải có `review_status=review_required` cho đến
khi ground-truth quality gate được phê duyệt. `note_candidates` cũng chỉ là dữ
liệu review, không phải field đã duyệt.

## Warning và error

Warning không làm request thất bại. `success_with_warnings` bắt buộc có ít
nhất một warning. `success` bắt buộc không có warning. Warning không tự động
đồng nghĩa review; `review_status` là quyết định riêng.

Expected validation, rendering, OCR, layout và filesystem failures được map
thành result `failed`; không để stack trace thoát ra public payload. Error có:

- `code`: code trong catalog v1.
- `message`: thông báo an toàn cho caller, không chứa internal path/stack.
- `stage`: stage ổn định.
- `retryable`: boolean.
- `details`: object đã khử dữ liệu nhạy cảm hoặc `null`.

Khi failed, `review_status=review_required`, `business=null`; diagnostic
artifacts đã ghi thành công trước lỗi vẫn có thể xuất hiện trong manifest.

Catalog máy đọc được nằm tại `contracts/local_api/v1/error_catalog.json`. Mười hai
`ErrorCode` và bảy `ErrorStage` của schema v1 được giữ nguyên. Mỗi entry khóa stage,
`retryable` và public message; riêng lỗi workspace phân biệt collision/security
(không retry) với lỗi ghi tạm thời (có thể retry). Exception gốc được chain nội bộ
để debug nhưng không xuất hiện trong result public.

## Progress và structured logging

Public Python API nhận `progress: Callable[[ProgressEvent], None] | None`.
`ProgressEvent` bất biến, gồm `correlation_id`, `stage`, `event`, `completed`,
`total`, `message`, `page_number` và `terminal`. `total` luôn bằng `100`;
`completed` nằm trong `0..100`, tăng đơn điệu và success luôn kết thúc bằng đúng
một terminal event `100/100`. Failure phát terminal event tại mức tiến độ gần nhất,
không giả vờ hoàn tất 100%. Callback ném exception không làm hỏng OCR: runtime ghi
event `progress_callback_failed`, vô hiệu callback trong phần còn lại của call và
vẫn trả terminal result thật.

Mọi service event đồng thời được ghi dạng JSON Lines với tối thiểu
`timestamp`, `level`, `correlation_id`, `stage`, `event`, `completed`, `total` và
`terminal`; `page_number` chỉ có khi áp dụng. Mặc định log không chứa input/output
path, tên PDF, OCR text, exception message, traceback hoặc stack. Chỉ môi trường
debug riêng tư được bật `include_exception_trace=True`; cờ này không thay đổi public
result. CLI ghi structured service logs vào stderr và giữ stdout là đúng một machine
JSON (hoặc rỗng khi dùng `--output-json`). Callback ba đối số của orchestrator vẫn
được giữ cho Debug UI và không phải public service callback.

## Artifact boundary

Request được phép chứa absolute local paths. Result không được lặp lại
`input_pdf`, `output_root`, image path hoặc temporary path. Mỗi artifact gồm
opaque `artifact_id`, `kind`, `relative_path`, `media_type`, SHA-256 và size.
`relative_path` được resolve dưới request `output_root`; không được absolute,
chứa `..`, symlink/reparse escape hoặc secret.

Mỗi call giữ độc quyền workspace xác định `output_root/<correlation_id>`. Bất kỳ
workspace đã tồn tại, kể cả thư mục rỗng, đều là collision và không bị tái sử dụng.
Runtime từ chối symlink/Windows reparse point tại output root, workspace và mọi
artifact; artifact chỉ được ghi dưới workspace đã có marker hợp lệ.

Khi kết thúc success hoặc failure, runtime ghi nguyên tử
`artifact_manifest.json` UTF-8. Manifest vật lý chứa SHA-256, số byte của từng
artifact, hash source trước/sau và cờ `source_unchanged`; manifest là public
artifact nhưng không tự liệt kê chính nó. Failure có thể giữ các partial artifact
đã ghi an toàn. Cleanup mặc định chỉ lập kế hoạch dry-run và chỉ xóa đúng workspace
có marker hợp lệ khi caller truyền xác nhận tường minh; contract không tự áp dụng
retention/quota.

## Lifecycle đồng bộ

1. Validate request và local paths.
2. Xác nhận một PDF_x, tạo workspace.
3. Render, detect, recognise và phân tích page roles.
4. Tổng hợp business result, warnings và review status.
5. Ghi artifacts/manifest, kết thúc timing.
6. Trả đúng một terminal result. Expected failures tại bất kỳ stage nào được
   map sang failure envelope cùng `correlation_id`.

Không có background job, polling, cancellation, retry nội bộ hoặc HTTP trong
contract v1.

## Backward compatibility

- Thêm optional field có thể giữ schema version 1.x nếu consumer cũ bỏ qua.
- Xóa/đổi tên field, đổi type/nullability, đổi enum semantics hoặc đổi artifact
  path base là breaking change và phải tăng major schema version.
- `pipeline_version` có thể đổi độc lập nhưng runtime output luôn phải validate
  theo `schema_version` đã công bố.
- Đổi enum/error semantics, review gate hoặc artifact path trust boundary là
  breaking change và cũng phải tăng major version.
- Release v1 hiện chạy từ source checkout; repository root phải nằm trên
  `PYTHONPATH` khi consumer chạy từ cwd khác. Wheel/deployment artifact không thuộc
  contract đã khóa này.

## Local CLI JSON adapter

Consumer không chạy Python gọi cùng public service qua entry point:

```powershell
python -m src.relay_form_ocr `
  --input "D:\management-data\P_001.pdf" `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-123" `
  --json
```

CLI resolve đường dẫn tương đối thành tuyệt đối trước khi tạo `OcrRequest`. Cờ
`--json` được giữ để tương thích command mẫu; JSON luôn là định dạng duy nhất của
adapter. Nếu không có `--output-json`, stdout chứa đúng một JSON UTF-8 và newline cuối;
mọi log/model output được chuyển sang stderr. Nếu có `--output-json`, stdout rỗng và
typed result được ghi UTF-8 vào file. File đã tồn tại không bị ghi đè trừ khi caller
chủ động thêm `--overwrite-result`; khi đó replacement là nguyên tử.

Public service failure vẫn là `OcrResult` schema v1. Lỗi xảy ra trước typed request
hoặc trong chính adapter dùng envelope nhỏ riêng có `cli_schema_version=1.0`,
`status=failed`, `exit_code` và `error`; envelope này không giả lập correlation ID hoặc
business result chưa tồn tại.

| Exit code | Ý nghĩa |
|---:|---|
| `0` | `success` hoặc `success_with_warnings` hợp lệ. |
| `2` | Sai cú pháp CLI, tổ hợp option hoặc typed request validation. |
| `3` | Input không tồn tại/không phải file/không phải PDF hợp lệ. |
| `4` | Workspace, artifact hoặc result JSON không ghi được. |
| `5` | Render, detection, recognition, layout hoặc pipeline thất bại. |
| `70` | CLI adapter không thể tạo/serialize terminal result. |

Help (`--help`) là output dành cho người dùng và thoát `0`; machine invocation không
dùng help luôn tuân thủ quy ước JSON/stdout ở trên. Structured service logs đi tới
stderr; machine JSON trên stdout không bị trộn progress hoặc log.

## Consumer reference và review gate

Reference implementation nằm tại `examples/local_consumer/`. Python consumer gọi
trực tiếp `RelayFormOcrService` và chỉ import public symbols; PowerShell consumer gọi
public CLI qua subprocess. Cả hai validate terminal result, resolve artifact relative
path dưới `output_root`, đọc physical manifest, kiểm tra source bất biến, size và
SHA-256 trước khi quyết định:

- `ready_for_use`: xử lý thành công và `review_status=not_required`.
- `manual_review_required`: xử lý thành công nhưng cần người duyệt; không đồng nghĩa
  approved và không được tự ghi candidate vào dữ liệu chính thức.
- `failed`: OCR trả public error code/stage/retryable.
- `consumer_failure`: schema, stream, manifest, path, size hoặc checksum không hợp lệ;
  consumer từ chối toàn bộ result.

Sanitized consumer summary không chứa source/output absolute path, OCR text, public
error message hay traceback. Python example cô lập cả Python stdout và native file
descriptor output của model sang stderr trước khi ghi đúng một summary JSON. Khi chạy
từ source checkout ở thư mục consumer riêng, repository root phải có trong
`PYTHONPATH`; installable deployment package vẫn thuộc kế hoạch packaging sau.

## Acceptance fixtures

Bốn fixture UTF-8 nằm tại `contracts/local_api/v1/examples/`:

- `success.json`
- `success_with_warnings.json`
- `review_required.json`
- `failure.json`

Chúng là contract examples đã được phía OCR và human đại diện consumer xác nhận
trong gate của IMMEDIATE-001. Cả bốn fixture validate bằng typed models và JSON Schema
export của IMMEDIATE-003; public service của IMMEDIATE-004 trả trực tiếp `OcrResult`.
