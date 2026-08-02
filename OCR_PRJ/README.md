# OCR_PRJ — Local API v1

OCR_PRJ cung cấp pipeline OCR phiếu chỉnh định rơ-le và một **local application
API v1** để chương trình khác trên cùng máy xử lý đồng bộ từng PDF_x. Interface
chuẩn là Python; CLI JSON là adapter cho consumer dùng runtime khác.

Trạng thái version đã khóa:

| Thành phần | Version |
|---|---:|
| Local API | `1.0` |
| Request/result schema | `1.0` |
| CLI error envelope | `1.0` |
| Pipeline implementation | `0.7.0` |

Đây là integration v1 chạy từ source checkout, chưa phải package triển khai độc
lập. Page 3+ và phần Lưu ý luôn cần người duyệt; acceptance hiện tại không phải
phép đo accuracy vì chưa có ground truth.

## Bắt đầu nhanh trên Windows

Yêu cầu Python 64-bit 3.10–3.12. Sau khi clone:

```powershell
git clone <repository-url> OCR_PRJ
Set-Location OCR_PRJ

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\setup_debug_ui.ps1

powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Script setup tạo `.venv`, cài toàn bộ OCR/PDF runtime, kiểm tra Poppler và warm-up
VietOCR/PaddleOCR. Lần setup đầu có thể cần network để tải dependency hoặc model
chưa có trong cache. Nếu `.venv` cũ trỏ tới Python đã bị gỡ, chạy lại với
`-RecreateVenv`.

Smoke test public import:

```powershell
$env:PYTHONPATH = (Get-Location).Path
& ".\.venv\Scripts\python.exe" -c `
  "from src.relay_form_ocr import OcrRequest, OcrResult, RelayFormOcrService, ProgressEvent, PIPELINE_VERSION; print(PIPELINE_VERSION)"
```

## Python API

```python
from pathlib import Path
from src.relay_form_ocr import OcrRequest, RelayFormOcrService

service = RelayFormOcrService()  # giữ instance này để tái sử dụng model
result = service.process_pdf(
    OcrRequest(
        input_pdf=Path(r"D:\management-data\P_001.pdf"),
        output_root=Path(r"D:\ocr-artifacts"),
        correlation_id="ticket-123",
    )
)

if result.status.value == "failed":
    print(result.error.code.value, result.error.retryable)
elif result.review_status.value == "review_required":
    print("Cần người duyệt; không tự động ghi candidate vào dữ liệu chính thức")
else:
    print(result.business)
```

Chi tiết request/result, progress callback, artifact audit, GPU, error handling và
consumer example nằm trong [API.md](API.md).

## CLI JSON

```powershell
$env:PYTHONPATH = (Get-Location).Path
& ".\.venv\Scripts\python.exe" -m src.relay_form_ocr `
  --input "D:\management-data\P_001.pdf" `
  --output-root "D:\ocr-artifacts" `
  --correlation-id "ticket-123" `
  --json
```

Machine JSON nằm trên stdout; structured logs/model output nằm trên stderr. Dùng
`--output-json <file>` để ghi result vào file và giữ stdout rỗng. CLI không tự ghi
đè result file hoặc workspace đã tồn tại.

## Phạm vi hỗ trợ

- Một PDF_x local cho mỗi synchronous call.
- Public Python API hoặc local CLI JSON trên cùng máy.
- Unicode path trên Windows.
- Typed terminal result, progress callback, error catalog ổn định.
- Workspace riêng, source hash, manifest, artifact size và SHA-256.

Ngoài phạm vi v1: PDF_A, folder/multiple inputs, HTTP, network transport,
background queue, distributed storage và production auto-accept. Page 2 hiện bị
skip có warning; Table 02 của Page 1 chưa được trích xuất.

## Kiểm thử

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1

& ".\.venv\Scripts\python.exe" `
  -m scripts.local_api_v1_handoff --check-only
```

Acceptance đã chạy 10/10 executions trên 8 layout families, 69 trang thật, với
repeatability, invalid-PDF failure, source immutability và full artifact audit.
Mọi kết quả thật vẫn là `review_required`.

## Tài liệu

- [API.md](API.md) — hướng dẫn tích hợp đầy đủ cho team.
- [ARCHITECTURE.md](ARCHITECTURE.md) — kiến trúc, data flow và trust boundary.
- [Local API contract v1](docs/LOCAL_API_CONTRACT_V1.md) — contract chuẩn.
- [Manual](manual.md) — lệnh sửa đổi, test, E2E và visual review chi tiết.
- [Immediate plan](immediate.md) — trạng thái integration ngắn hạn.
- [Long-term plan](plan.md) — ground truth, packaging, deployment và UAT.
- [Session handoff](session-handoff.md) — điểm tiếp tục cho phiên sau.

## Quy tắc thay đổi v1

Có thể thêm optional field trong v1 chỉ khi fixture và consumer cũ vẫn hợp lệ.
Xóa/đổi tên field, đổi type/nullability/enum/error semantics hoặc artifact path
boundary là breaking change và phải tăng major version. `pipeline_version` có thể
đổi độc lập nếu output vẫn validate theo schema đã công bố.
