# Hệ thống Quản lý Rơ-le Kỹ thuật số (EVN RMS)

Hệ thống EVN RMS (Relay Management System) là một ứng dụng quản lý hiện đại, được thiết kế đặc biệt cho ngành Điện lực (EVN) nhằm số hóa quy trình quản lý Cấu hình Rơ-le bảo vệ, Phân quyền người dùng và Ký số (Digital Signature).

Dự án được xây dựng trên nền tảng **Django (Python)** kết hợp với **PostgreSQL**, **HTMX** và **TailwindCSS**, mang lại giao diện Premium siêu nhanh và trải nghiệm mượt mà không cần tải lại trang (SPA-like).

---

## 🌟 Tính năng Nổi bật

### 1. Phân quyền & Vai trò tự động (Auto RBAC)
Hệ thống tự động thiết lập 5 Vai trò chính (Kèm phân quyền) ngay khi khởi tạo:
- **Quản trị viên (Admin):** Toàn quyền kiểm soát hệ thống (Tài khoản, quyền hạn, cấu hình hệ thống).
- **Điều phối viên (Dispatcher):** Tạo phiếu, chạy AI OCR, rà soát tính hợp lệ của phiếu và phân công công việc.
- **Trưởng nhóm Trạm (Station Leader):** Quản lý chung tại trạm, tiếp nhận phân công.
- **Kỹ thuật viên (Technician):** Trực tiếp xuống trạm thực hiện cấu hình Rơ-le và ký số hoàn thành.
- **Giám sát trạm (Supervisor):** Giám sát tại trạm, rà soát thông số KTV vừa nhập và ký xác nhận nghiệm thu.

### 2. Luồng Ký số Đa bước (Multi-step Digital Signatures)
- **Giả lập SmartCA:** Ký số mô phỏng chính xác giao diện hệ thống EVN SmartCA với mã PIN xác thực.
- **Quy trình chuẩn mực:** Phân công -> Tiếp nhận -> Thực thi -> Giám sát -> Phê duyệt.
- **Trục tiến trình (Stepper):** Trực quan hóa tiến độ Ký số với các biểu tượng thay đổi theo trạng thái.

### 3. Dashboard Thống kê (Real-time Analytics)
- Trực quan hóa dữ liệu bằng **Chart.js**.
- Giao diện linh hoạt, tự động thay đổi theo vai trò đăng nhập.
- Giao diện thẻ Thống kê 3D (Hover effect, Glassmorphism).

### 4. Giao diện (UI/UX) Chuẩn mực & Tối ưu
- Ngôn ngữ: 100% Tiếng Việt, phong cách Clean & Minimalist.
- Sử dụng **TailwindCSS** với Tone màu xanh EVN chủ đạo.

---

## 🛠 Công nghệ Sử dụng
- **Backend:** Django 6.x / Python 3.13 / ASGI (Daphne)
- **Frontend:** HTMX, TailwindCSS, FontAwesome 6, Chart.js
- **Database:** PostgreSQL 15
- **Deploy:** Docker & Docker Compose

---

## 🚀 Cài đặt & Triển khai nhanh bằng Docker

Hệ thống được đóng gói 100% bằng Docker, giúp việc triển khai lên máy chủ cực kỳ đơn giản.

### 1. Tải mã nguồn về máy chủ
```bash
git clone https://github.com/xh1712006-debug/electric.git
cd electric
```

### 2. Khởi động hệ thống
```bash
docker-compose up -d --build
```
Lệnh này sẽ tự động:
- Cài đặt thư viện Python, tải Frontend.
- Khởi tạo Database PostgreSQL.
- Chạy các lệnh `migrate` và **tự động nạp phân quyền (seed_permissions)**.
- Tạo tài khoản Superuser mặc định.
- Chạy Server trên cổng `9000`.

### 3. Đăng nhập
- Truy cập vào: `http://<IP-Máy-Chủ>:9000` (hoặc domain của bạn).
- Tài khoản quản trị mặc định:
  - **Tài khoản:** `admin`
  - **Mật khẩu:** `999999` (có thể thay đổi trong `.env` hoặc đổi sau khi đăng nhập).

---

## 💻 Chạy trên máy cá nhân (Local Development)

Nếu bạn muốn code và chạy trực tiếp bằng lệnh `runserver` trên máy Windows thay vì Docker:

1. Chạy riêng Database bằng Docker:
   ```bash
   docker-compose up -d db
   ```
2. Cài môi trường ảo và thư viện:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Chạy Server:
   ```powershell
   python manage.py runserver
   ```
