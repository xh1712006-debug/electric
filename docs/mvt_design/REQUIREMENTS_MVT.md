# Đặc tả Yêu cầu Hệ thống (SRS)
**Dự án:** Hệ thống Quản lý Phiếu Chỉnh định Rơ-le (RMS)
**Kiến trúc:** Django (MVT) + PostgreSQL

## 1. Tổng quan Hệ thống
RMS là hệ thống web phục vụ quy trình lập phiếu, phê duyệt, chuyển giao và xác nhận hoàn thành công tác chỉnh định thông số bảo vệ rơ-le tại các trạm biến áp.
Hệ thống được thiết kế lại hoàn toàn theo kiến trúc **MVT của Django**, sử dụng **PostgreSQL làm cơ sở dữ liệu chính**.

## 2. Kiến trúc Công nghệ
- **Mô hình:** MVT (Model - View - Template)
- **Framework:** Django
- **Cơ sở dữ liệu:** PostgreSQL
- **Giao diện (Frontend):** Django Templates kết hợp TailwindCSS/Bootstrap (Sử dụng HTMX/Alpine.js cho tương tác AJAX động).
- **Tích hợp bên ngoài:** Hệ thống Ký số EVN (qua REST API).

## 3. Các Phân hệ Chức năng & Luồng Nghiệp vụ
### 3.1 Xác thực & Phân quyền (Auth & RBAC)
- Sử dụng Session Authentication mặc định của Django.
- **Vai trò:** A0/A1 (Phát hành), VTC/Vận hành/Điều độ (Rà soát), Kỹ thuật viên (Chỉnh định), Giám sát trạm (Xác nhận), Admin.
- Sử dụng `django.contrib.auth.models.Group` kết hợp custom model mở rộng.

### 3.2 Quản lý Trạm biến áp & Rơ-le
- CRUD thông tin Trạm biến áp (Station), Ngăn lộ (Bay), Rơ-le (Relay).
- **Upload File Cấu hình:** Người dùng upload JSON/Excel. Hệ thống xử lý và lưu vào các bảng quan hệ của PostgreSQL.

### 3.3 Quản lý Phiếu Chỉnh định (Sheet Lifecycle)
- **Khởi tạo & Upload:** A0/A1 chọn trạm, upload file PDF/JPG bản scan phiếu. Form hỗ trợ nhập metadata tạm thời (khi OCR chưa sẵn sàng) và lưu vào `JSONField` của PostgreSQL.
- **Phát hành (Ký số lần 1):** Click nút Ký số, Django View sẽ gọi API Ký số EVN và mở iframe cho A0/A1 thao tác. Xác nhận thành công sẽ chuyển trạng thái sang `PENDING_REVIEW`.
- **Rà soát Đa lớp:** VTC/Vận hành vào màn hình "Chờ rà soát", đối chiếu bản scan và thông số, chọn "Phê duyệt" hoặc "Từ chối". Phê duyệt xong chuyển thành `ASSIGNED_TO_SC`.
- **Chuyển giao:** Công ty Truyền tải gán KTV phụ trách.
- **Xác nhận hoàn thành (Ký số lần 2 & 3):** KTV chỉnh định xong, thực hiện Ký số. Sau đó Giám sát trạm ký xác nhận. Phiếu cập nhật thành `COMPLETED`.

### 3.4 Kiểm tra Định kỳ (Periodic Checks)
- Giao diện dạng bảng lưới (Grid) hiển thị các thông số tiêu chuẩn của Rơ-le.
- Người dùng nhập kết quả đo thực tế, nhấn "Lưu". Logic View tính toán sai lệch % và cảnh báo (ĐẠT / VƯỢT NGƯỠNG).

## 4. Giải pháp Kỹ thuật Lưu trữ với PostgreSQL
- **JSONB / Schemaless Data:** Các thông số `extracted_data` (từ OCR hoặc tự nhập) sẽ được lưu dưới dạng kiểu dữ liệu `JSONField` (JSONB) của PostgreSQL, kết hợp sức mạnh truy vấn NoSQL trong môi trường cơ sở dữ liệu quan hệ (RDBMS).
- **Tính toàn vẹn dữ liệu (Data Integrity):** PostgreSQL cung cấp các ràng buộc khóa ngoại (Foreign Keys) để đảm bảo tính toàn vẹn dữ liệu giữa các bảng như Trạm, Ngăn lộ, Rơ-le và Phiếu chỉnh định.
