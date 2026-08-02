# Hướng dẫn tích hợp Local OCR API v1

Tài liệu này dành cho thành viên trong team clone OCR_PRJ và muốn gọi pipeline từ
một ứng dụng khác trên cùng máy. Nếu chỉ cần chạy thử nhanh, bắt đầu ở
[README.md](README.md). Contract chuẩn nằm tại
[docs/LOCAL_API_CONTRACT_V1.md](docs/LOCAL_API_CONTRACT_V1.md).

## 1. Phiên bản và trạng thái

| Thành phần            | Version | Ý nghĩa                                       |
| --------------------- | ------: | --------------------------------------------- |
| Local API             |   `1.0` | Public Python interface và hành vi lifecycle. |
| Request/result schema |   `1.0` | Pydantic models và JSON Schema.               |
| CLI schema            |   `1.0` | Envelope cho lỗi xảy ra trước typed request.  |
| Pipeline              | `0.7.0` | Phiên bản implementation OCR hiện tại.        |

V1 đã vượt qua acceptance về contract, repeatability, workspace, failure và
artifact integrity. Nó chưa có ground truth đủ để công bố OCR accuracy và chưa
được đóng gói thành wheel/service deployment độc lập.

## 2. Clone và chuẩn bị runtime

Yêu cầu:

- Windows 10/11 64-bit.
- Python 3.10–3.12 64-bit.
- Quyền đọc thư mục PDF input và quyền tạo output root.
- Dung lượng đĩa đủ cho ảnh render, OCR JSON và evidence.
- Network ở lần cài đầu nếu dependency/model chưa có trong cache.

```powershell
git clone https://github.com/provincevu/OCR_PRJ.git
Set-Location OCR_PRJ

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_debug_ui.ps1
```

Script tạo `.venv`, cài full OCR runtime, kiểm tra dependency/Poppler và warm-up
VietOCR + PaddleOCR. Nếu không muốn warm-up model trong bước setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_debug_ui.ps1 -SkipModelWarmup
```

Xác minh repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

## 3. Import khi chạy từ source checkout

Repository hiện chưa có `pyproject.toml`/wheel chính thức. Khi chương trình chạy
từ root repository, Python tự thấy package `src`. Khi chạy từ thư mục/process
khác, thêm **repository root** vào `PYTHONPATH` trước khi khởi động process:

```powershell
$projectRoot = (Resolve-Path "D:\source\OCR_PRJ").Path
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
  $projectRoot
} else {
  $projectRoot + [System.IO.Path]::PathSeparator + $env:PYTHONPATH
}

& "$projectRoot\.venv\Scripts\python.exe" -c `
  "from src.relay_form_ocr import OcrRequest, OcrResult, RelayFormOcrService, ProgressEvent, PIPELINE_VERSION; print(PIPELINE_VERSION)"
```

Không thêm `src\relay_form_ocr` trực tiếp vào `PYTHONPATH`; public module đúng là
`src.relay_form_ocr`. Installable packaging thuộc PLAN-009/PLAN-018.

## 4. Public Python API tối thiểu

Ba class chính:

```python
from src.relay_form_ocr import OcrRequest, OcrResult, RelayFormOcrService
```

Ví dụ xử lý một PDF_x:

```python
from pathlib import Path
from src.relay_form_ocr import (
    OcrRequest,
    ProcessingStatus,
    RelayFormOcrService,
    ReviewStatus,
)

input_pdf = Path(r"D:\management-data\P_001.pdf").resolve()
output_root = Path(r"D:\ocr-artifacts").resolve()

# Nên giữ service sống lâu và dùng tuần tự để tái sử dụng model đã load.
service = RelayFormOcrService()
result = service.process_pdf(
    OcrRequest(
        input_pdf=input_pdf,
        output_root=output_root,
        correlation_id="ticket-123",
    )
)

if result.status is ProcessingStatus.FAILED:
    assert result.error is not None
    print(result.error.code.value, result.error.stage.value, result.error.retryable)
elif result.review_status is ReviewStatus.REVIEW_REQUIRED:
    print("OCR hoàn tất nhưng cần người duyệt")
else:
    print("Kết quả vượt qua review gate")
```

`process_pdf` chạy đồng bộ: hàm chỉ trả sau khi hoàn tất hoặc có terminal failure.
Không gọi đồng thời cùng service instance nếu chưa có concurrency policy được duyệt.

### OcrRequest

Request chỉ nhận đúng ba field và từ chối field lạ:

| Field            | Quy tắc                                                                 |
| ---------------- | ----------------------------------------------------------------------- |
| `input_pdf`      | Absolute `Path` tới đúng một file `.pdf`; consumer cam kết đó là PDF_x. |
| `output_root`    | Absolute `Path` mà OCR process được phép ghi.                           |
| `correlation_id` | 1–128 ký tự ASCII; bắt đầu chữ/số, sau đó chỉ chữ/số, `.`, `_`, `-`.    |

Mỗi correlation ID tạo workspace `output_root/<correlation_id>`. Workspace đã tồn
tại, kể cả rỗng, là collision. Dùng correlation ID mới cho retry/rerun; không xóa
workspace cũ trước khi đã lưu evidence cần thiết.

### Giữ và tái sử dụng model

```python
service = RelayFormOcrService()
for item in pdf_jobs:  # xử lý tuần tự
    result = service.process_pdf(item)
```

Tạo service mới cho mỗi PDF sẽ load model lại và làm tăng mạnh latency/RAM. V1
chưa khóa multi-thread/multi-process concurrency hoặc resource limits.

### Chạy GPU

```python
service = RelayFormOcrService(use_gpu=True)
```

Chỉ bật khi cả PyTorch CUDA và PaddlePaddle CUDA phù hợp driver đã được cài. Script
setup mặc định không cam kết cài CUDA build. Kiểm tra trước bằng acceptance runner:

```powershell
& ".\.venv\Scripts\python.exe" `
  -m examples.local_consumer.acceptance_runner plan `
  --corpus ".\contracts\local_api\v1\acceptance_corpus.json" `
  --input-root ".\data\pdf" `
  --device gpu
```

Preflight GPU thoát 40 trước khi tạo run workspace nếu một trong hai runtime không
sẵn sàng.

## 5. Progress callback và structured logging

```python
import logging
import sys
from src.relay_form_ocr import (
    JsonLineFormatter,
    OcrRequest,
    ProgressEvent,
    RelayFormOcrService,
)

logger = logging.getLogger("management.ocr")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(JsonLineFormatter())
logger.addHandler(handler)
logger.propagate = False

def on_progress(event: ProgressEvent) -> None:
    print(
        f"{event.completed:3d}% {event.stage.value} {event.event}",
        file=sys.stderr,
    )

service = RelayFormOcrService(logger=logger)
result = service.process_pdf(request, progress=on_progress)
```

`completed` tăng đơn điệu trong `0..100`. Success có đúng một terminal 100/100;
failure kết thúc ở tiến độ thật. Callback ném exception không làm OCR thất bại:
callback bị tắt sau lỗi đầu và service tiếp tục trả terminal result.

Log mặc định được khử PDF path, OCR text và exception trace. Chỉ bật
`include_exception_trace=True` trong môi trường debug riêng tư; không gửi log đó
ra public/shared channel.

## 6. Đọc và quyết định từ OcrResult

Top-level result luôn có:

- `schema_version`, `pipeline_version`, `correlation_id`.
- `status`, `review_status`.
- `document`, `business`, `pages`, `warnings`.
- `timing`, `artifact_manifest`, `error`.

Quy tắc quan trọng:

```python
from src.relay_form_ocr import ProcessingStatus, ReviewStatus

if result.status is ProcessingStatus.FAILED:
    # business luôn null; xử lý result.error
    ...
elif result.review_status is ReviewStatus.REVIEW_REQUIRED:
    # giữ candidate để người duyệt; KHÔNG ghi như dữ liệu đã approved
    ...
else:
    # vẫn cần policy nghiệp vụ của hệ thống tích hợp
    ...
```

`success_with_warnings` vẫn là xử lý thành công về kỹ thuật. Nó không tự động có
nghĩa dữ liệu đúng hoặc đã được duyệt. Page 3+ setting records và note candidates
luôn `review_required` trong v1.

### Page 1

Khi Page 1 xử lý thành công, `business.page1_fields` có đủ 25 canonical keys. Mỗi
field gồm value, confidence, resolution status và source page. Value có thể `null`;
consumer không được dịch chuyển field hoặc tự đoán từ field kế bên.

### Page 2 và Page 3+

- Page 2 hiện có `skipped_by_policy` và warning.
- Page 1 Table 02 chưa được trích xuất.
- Page 3+ và Lưu ý là candidate bắt buộc duyệt.

## 7. Error handling và retry

Request model không hợp lệ làm Pydantic raise `ValidationError` trước khi OCR chạy.
Expected runtime failures trả `OcrResult(status=failed)` với public error:

```python
if result.error is not None:
    code = result.error.code.value
    stage = result.error.stage.value
    if result.error.retryable:
        schedule_retry_with_new_correlation_id()
    else:
        send_to_operator(code, stage)
```

Không parse `message` để điều khiển nghiệp vụ; dùng `code`, `stage`, `retryable`.
Catalog đầy đủ: [error_catalog.json](contracts/local_api/v1/error_catalog.json).
Public result không chứa raw exception hoặc traceback.

## 8. Artifact và integrity audit

Artifact public chỉ có relative POSIX path. Luôn resolve dưới `output_root`, chặn
absolute path, `..`, backslash và path thoát root. Sau đó kiểm tra size/SHA-256.
Reference implementation hoàn chỉnh nằm trong
[python_consumer.py](examples/local_consumer/python_consumer.py).

Ví dụ rút gọn:

```python
from hashlib import sha256
from pathlib import Path, PurePosixPath

root = output_root.resolve()
for artifact in result.artifact_manifest.artifacts:
    relative = PurePosixPath(artifact.relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("unsafe artifact path")
    path = root.joinpath(*relative.parts).resolve()
    if root not in path.parents:
        raise ValueError("artifact escaped output root")
    data = path.read_bytes()
    if len(data) != artifact.size_bytes:
        raise ValueError("artifact size mismatch")
    if sha256(data).hexdigest() != artifact.sha256:
        raise ValueError("artifact checksum mismatch")
```

Physical `artifact_manifest.json` còn ghi source hash trước/sau và
`source_unchanged`. Reference consumer kiểm tra cả public và physical manifest;
nên tái sử dụng consumer này thay vì tự viết audit tối giản trong production.

## 9. Serialize JSON

```python
payload = result.model_dump(mode="json")
json_text = result.model_dump_json(indent=2)

# Validate payload nhận từ process/ổ đĩa khác:
validated = OcrResult.model_validate_json(json_text)
```

JSON dùng UTF-8. Không dùng `str(result)` làm wire format.

## 10. CLI adapter

CLI gọi đúng cùng `RelayFormOcrService`:

```powershell
$projectRoot = (Resolve-Path "D:\source\OCR_PRJ").Path
$pythonExe = "$projectRoot\.venv\Scripts\python.exe"
$env:PYTHONPATH = $projectRoot

& $pythonExe -m src.relay_form_ocr `
  --input "D:\management-data\P_001.pdf" `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-123" `
  --json
```

Không có `--output-json`: stdout chứa đúng một JSON UTF-8; stderr chứa log. Ghi ra
file:

```powershell
& $pythonExe -m src.relay_form_ocr `
  --input "D:\management-data\P_001.pdf" `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-124" `
  --output-json "D:\management-data\results\ticket-124.json"
```

File result có sẵn không bị ghi đè. Chỉ thêm `--overwrite-result` khi caller chủ
động chấp nhận atomic replacement; option này bắt buộc đi cùng `--output-json`.

### Đọc CLI trong PowerShell

```powershell
$stderrFile = Join-Path $env:TEMP "ocr-ticket-125.stderr.log"
$stdoutLines = @(& $pythonExe -m src.relay_form_ocr `
  --input "D:\management-data\P_001.pdf" `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-125" `
  --json 2> $stderrFile)
$ocrExitCode = $LASTEXITCODE
$result = ($stdoutLines -join "`n") | ConvertFrom-Json
```

| Exit | Ý nghĩa                                           |
| ---: | ------------------------------------------------- |
|    0 | Typed `success` hoặc `success_with_warnings`.     |
|    2 | CLI usage hoặc request validation.                |
|    3 | Input/PDF không hợp lệ.                           |
|    4 | Workspace/artifact/result output lỗi.             |
|    5 | Rendering/OCR/layout/pipeline lỗi.                |
|   70 | Adapter không tạo/serialize được terminal output. |

Lỗi trước khi tạo typed request dùng `cli_schema_version=1.0`; không giả lập
`OcrResult`. Kiểm tra cả exit code và JSON envelope.

## 11. Consumer mẫu nên tái sử dụng

Python consumer từ root repository:

```powershell
& ".\.venv\Scripts\python.exe" `
  -m examples.local_consumer.python_consumer `
  --input "D:\management-data\P_001.pdf" `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-126" `
  --summary-json "D:\management-data\results\ticket-126-summary.json"
```

PowerShell wrapper cho process khác:

```powershell
& ".\examples\local_consumer\invoke_ocr.ps1" `
  -InputPdf "D:\management-data\P_001.pdf" `
  -OutputRoot "D:\ocr-artifacts" `
  -CorrelationId "ticket-127" `
  -ProjectRoot (Get-Location).Path `
  -PythonExe ".\.venv\Scripts\python.exe"
```

Consumer trả bốn outcome an toàn: `ready_for_use`, `manual_review_required`,
`failed`, `consumer_failure`. Schema/path/manifest/checksum sai làm consumer từ
chối toàn result.

## 12. Cleanup workspace

Luôn dry-run trước:

```powershell
& ".\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.workspace_cleanup `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-123"
```

Chỉ xóa khi đã kiểm tra đúng workspace và không còn cần evidence:

```powershell
& ".\.venv\Scripts\python.exe" `
  -m src.relay_form_ocr.workspace_cleanup `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-123" `
  --confirm-delete
```

Cleanup chỉ nhận workspace có marker hợp lệ. V1 chưa có retention/quota tự động.

## 13. Contract, schema và fixture

- [Release manifest](contracts/local_api/v1/release_manifest.json)
- [Contract manifest](contracts/local_api/v1/contract_manifest.json)
- [Request JSON Schema](contracts/local_api/v1/schemas/ocr_request.schema.json)
- [Result JSON Schema](contracts/local_api/v1/schemas/ocr_result.schema.json)
- [Success example](contracts/local_api/v1/examples/success.json)
- [Warning example](contracts/local_api/v1/examples/success_with_warnings.json)
- [Review-required example](contracts/local_api/v1/examples/review_required.json)
- [Failure example](contracts/local_api/v1/examples/failure.json)

Không copy schema bằng tay sang project consumer. Nên pin repository revision hoặc
chép đúng tracked schema/fixture cùng release manifest.

## 14. Kiểm thử integration

Full repository verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Handoff/schema/link/public command checks:

```powershell
& ".\.venv\Scripts\python.exe" `
  -m unittest tests.test_local_api_handoff -v

& ".\.venv\Scripts\python.exe" `
  -m scripts.local_api_v1_handoff --check-only
```

Kiểm tra lại acceptance evidence mà không OCR lại corpus:

```powershell
& ".\.venv\Scripts\python.exe" `
  -m examples.local_consumer.acceptance_runner verify `
  --manifest ".\output\local_acceptance\immediate-009-cpu-20260731\acceptance_manifest.json" `
  --full-artifact-audit
```

Acceptance output bị ignore khỏi Git; clean clone cần chạy corpus lại hoặc nhận
evidence bundle từ máy nghiệm thu trước khi dùng lệnh verify này.

## 15. Quy tắc backward compatibility

Trong v1 có thể thêm optional field nếu consumer cũ bỏ qua field lạ theo contract
đã thỏa thuận và toàn bộ fixture cũ vẫn hợp lệ. Các thay đổi sau bắt buộc tăng
major version:

- Xóa hoặc đổi tên public field.
- Đổi type/nullability.
- Đổi ý nghĩa enum, status, error code/stage/retryable.
- Đổi artifact path base hoặc trust boundary.
- Biến review candidate thành approved data mặc định.

`pipeline_version` có thể thay đổi độc lập, nhưng result phải validate theo
`schema_version` được công bố. Khi sửa contract, cập nhật đồng thời typed model,
JSON Schema, fixtures, release manifest, README, API.md, contract tests và consumer
tests.

## 16. Troubleshooting

### `ModuleNotFoundError: No module named 'src'`

Process đang chạy ngoài repository và thiếu repository root trên `PYTHONPATH`.
Thiết lập như mục 3 trước khi khởi động process.

### `.venv\Scripts\python.exe` không tồn tại hoặc không chạy

Chạy setup với `-RecreateVenv`. Không tái sử dụng venv đã được copy từ máy khác.

### Model tải lại ở mọi request

Caller đang tạo `RelayFormOcrService` mới cho từng PDF. Giữ một instance và xử lý
tuần tự.

### `workspace already exists`

Correlation ID đã được dùng. Đây là cơ chế chống ghi đè, không phải lỗi cần bỏ qua.
Dùng ID mới hoặc chạy cleanup có xác nhận sau khi đã audit/lưu evidence.

### stdout CLI không parse được JSON

Đảm bảo caller chỉ đọc stdout và chuyển stderr ra file/log riêng. Không trộn hai
stream. Dùng reference PowerShell consumer nếu có thể.

### Kết quả thành công nhưng vẫn `review_required`

Đây là hành vi đúng. Warning, Page 3+, note candidate hoặc confidence policy có thể
buộc review. Không sửa status ở phía consumer.

### GPU preflight không đạt

Kiểm tra driver và CUDA builds của cả PyTorch lẫn PaddlePaddle. Không ép
`use_gpu=True` nếu chỉ một framework nhìn thấy CUDA; dùng CPU cho đến khi preflight
đạt.

### PDF xử lý lâu

OCR CPU có thể mất nhiều phút/PDF. Giữ service để reuse model, theo dõi progress và
không chạy nhiều process cạnh tranh trước khi PLAN-016 khóa concurrency/resource
limits.
