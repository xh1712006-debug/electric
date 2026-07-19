# Hệ thống Quản lý Rơ-le Kỹ thuật số (EVN RMS)

Hệ thống EVN RMS (Relay Management System) là một ứng dụng quản lý hiện đại, được thiết kế đặc biệt cho ngành Điện lực (EVN) nhằm số hóa quy trình quản lý Cấu hình Rơ-le bảo vệ, Phân quyền người dùng và Ký số (Digital Signature).

Dự án được xây dựng trên nền tảng **Django (Python)** kết hợp với **HTMX** và **TailwindCSS**, mang lại giao diện Premium siêu nhanh và trải nghiệm mượt mà không cần tải lại trang (SPA-like).

---

## 🌟 Tính năng Nổi bật

### 1. Dashboard Thống kê (Real-time Analytics)
- Trực quan hóa dữ liệu bằng **Chart.js** cực kỳ mượt mà và sinh động.
- Giao diện linh hoạt, tự động thay đổi theo vai trò: 
  - **Quản lý/Điều độ:** Thống kê tổng quan về tiến độ phiếu, tỷ lệ trạng thái (Doughnut Chart) và số lượng phiếu 7 ngày qua (Bar Chart).
  - **Kỹ thuật viên:** Tập trung vào các Phiếu ưu tiên và lịch sử ký số cá nhân (Activity Feed).
- Giao diện thẻ Thống kê 3D (Hover effect, Glassmorphism).

### 2. Luồng Ký số Đa bước (Multi-step Digital Signatures)
- **Giả lập SmartCA:** Nút Ký số mô phỏng chính xác giao diện ký của hệ thống EVN SmartCA với mã PIN xác thực.
- **Quy trình chuẩn mực 3 cấp độ:** 
  1. Kỹ thuật viên (Chỉnh định & Thi công)
  2. Giám sát trạm (Xác nhận hoàn thành tại trạm)
  3. Điều độ viên (Duyệt kết quả đưa vào vận hành)
- **Trục tiến trình (Stepper):** Trực quan hóa tiến độ Ký số với các biểu tượng thay đổi theo trạng thái.

### 3. Phân quyền & Vai trò (Role-based Access Control - RBAC)
Hệ thống chuẩn hóa 5 Vai trò chính:
- **Quản trị viên (Admin):** Toàn quyền kiểm soát hệ thống.
- **Điều độ A0/A1 (Người tạo phiếu):** Khởi tạo phiếu mới, chạy AI OCR và quản lý CSDL Trạm/Thiết bị.
- **Điều phối viên (Gộp Rà soát & Điều độ):** Rà soát tính hợp lệ của phiếu từ A0/A1 và Phân công/Giao việc cho KTV.
- **Giám sát trạm (Supervisor):** Giám sát tại trạm, rà soát thông số KTV vừa nhập và ký xác nhận nghiệm thu.
- **Kỹ thuật viên (Technician):** Trực tiếp xuống trạm thực hiện cấu hình Rơ-le và ký số hoàn thành.

### 4. Giao diện (UI/UX) Chuẩn mực & Tối ưu
- Ngôn ngữ: 100% Tiếng Việt.
- Sử dụng **TailwindCSS** với Tone màu xanh EVN chủ đạo.
- Hỗ trợ Phân trang (Pagination) mượt mà cho các danh sách (Tài khoản, Trạm, Phiếu chỉnh định...).
- Tích hợp thanh tìm kiếm động (Dynamic Search).

---

## 🛠 Công nghệ Sử dụng
- **Backend:** Django 4.x / Python 3.10+
- **Frontend:** HTMX, TailwindCSS, FontAwesome 6, Chart.js
- **Database:** SQLite (Hỗ trợ chuyển đổi sang PostgreSQL/MySQL dễ dàng).

---

## 🚀 Cài đặt & Chạy dự án (Local)

1. **Clone repository:**
   ```bash
   git clone https://github.com/xh1712006-debug/electric.git
   cd electric
   ```

2. **Tạo và kích hoạt môi trường ảo (Virtual Environment):**
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   
   # Linux/MacOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Cài đặt thư viện:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Chạy Migration & Khởi tạo dữ liệu:**
   ```bash
   python manage.py migrate
   python manage.py seed_data
   ```

5. **Khởi động Server:**
   ```bash
   python manage.py runserver
   ```
   *Truy cập: `http://localhost:8000`*
