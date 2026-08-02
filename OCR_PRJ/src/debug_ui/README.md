# Giao diện gỡ lỗi PDF/OCR (Local PDF/OCR debug UI)

Giao diện Streamlit này chỉ gọi các dịch vụ production trong thư mục `src/`. Nó hỗ trợ hai luồng đầu vào:

1. Tải lên một `PDF_A` lớn, chia nó thành các file `PDF_x` cấp độ biểu mẫu, sau đó chọn kết quả nào sẽ được OCR.
2. Tải lên một hoặc nhiều file `PDF_x` cấp độ biểu mẫu có sẵn và bỏ qua bước chia tách.

Các file PDF được chọn sẽ được render và xử lý bởi các module phát hiện (detection) và nhận dạng (recognition) ở cấp production. Trang 1 sử dụng bộ phân tích trường cố định (fixed-field analyser), trang 2 cố tình bị bỏ qua, và trang 3+ sử dụng bộ tái tạo bảng cài đặt. Giao diện người dùng (UI) hiển thị raw OCR, hình ảnh, polygons, độ tin cậy (confidence), layout JSON, cảnh báo (warnings), và dữ liệu JSON trích xuất có thể tải xuống. Một phần `Lưu ý` có thể nhìn thấy được hiển thị dưới dạng một ứng viên raw OCR; nó không được trình bày như một ground truth có cấu trúc.

## Chuẩn bị và chạy (Windows)

Từ thư mục gốc (root) của repository, một lệnh duy nhất tạo một môi trường `.venv` production cô lập, cài đặt toàn bộ runtime phục vụ phát hiện/nhận dạng/PDF/UI, kiểm tra Poppler, khởi tạo cả hai mô hình OCR, và khởi động Streamlit:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_debug_ui.ps1 -Run
```

Quá trình cài đặt này không phụ thuộc vào thư mục `lab/`. Để chuẩn bị môi trường mà không mở UI, hãy bỏ cờ `-Run`. Các lần khởi chạy tiếp theo không cần lệnh kích hoạt (activation) và có thể sử dụng:

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run src\debug_ui\app.py
```

Warm-up mô hình được bật theo mặc định để các lỗi về tải xuống/thư viện gốc (native-library) xuất hiện ngay trong quá trình thiết lập thay vì xuất hiện ở lần trích xuất đầu tiên. Chỉ sử dụng `-SkipModelWarmup` khi một máy tính offline đã có sẵn các file mô hình.
Sử dụng `-SkipInstall` để chỉ chạy lại các bài kiểm tra môi trường. Yêu cầu Python 3.10-3.12 (64-bit). Trình cài đặt chỉ định rõ ràng PyTorch và TorchVision bởi vì VietOCR không khai báo chúng một cách nhất quán trong metadata package của mình. Nếu một `.venv` hiện có trỏ đến một bản cài đặt Python đã bị gỡ bỏ, hãy chạy `powershell -ExecutionPolicy Bypass -File scripts\setup_debug_ui.ps1 -RecreateVenv -Run` để bắt buộc tạo lại môi trường đó.

Trình duyệt mở tại địa chỉ `http://localhost:8501`. Các file tải lên, file PDF bị chia tách, các trang được render, bằng chứng OCR và dữ liệu JSON được lưu trữ theo từng phiên làm việc (session) tại thư mục `output/debug_ui/sessions/`, thư mục này được Git bỏ qua (ignored). Sử dụng nút trên thanh bên (sidebar) để xóa các artifacts của phiên làm việc hiện tại.

Cấu hình Streamlit của repository cho phép tải lên các file lớn lên tới 2 GB. Các đối tượng mô hình (model objects) được cache theo cấu hình GPU/DPI để đảm bảo tốc độ phản hồi nhanh khi gỡ lỗi lặp đi lặp lại.
