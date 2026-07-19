# Thiết kế Giao diện (Django Templates & UI)

Hệ thống theo kiến trúc MVT sẽ sử dụng bộ thư viện Frontend nhúng trực tiếp vào Django Templates.

## 1. Công nghệ Frontend
- **HTML/Template Engine:** Django Template Language (DTL)
- **CSS Framework:** TailwindCSS (via CDN hoặc pre-compiled) / Bootstrap 5.
- **Tương tác động (AJAX/DOM):** Sử dụng **HTMX** để thực hiện các thao tác Upload, Load dữ liệu không cần tải lại trang (Single Page App - like experience).
- **Icons:** FontAwesome / Heroicons.

## 2. Cấu trúc Thư mục Templates (`templates/`)

```text
templates/
│
├── base.html                  # Layout chính (Sidebar, Header, Footer)
├── auth/
│   ├── login.html             # Giao diện đăng nhập
│   └── password_reset.html    # Giao diện đổi mật khẩu
│
├── stations/
│   ├── station_list.html      # Bảng danh sách Trạm
│   ├── station_detail.html    # Chi tiết Trạm (Ngăn lộ, Rơ le)
│   └── import_form.html       # Form kéo thả file JSON/Excel
│
├── sheets/
│   ├── sheet_list.html        # Kanban board / Bảng danh sách Phiếu chỉnh định
│   ├── sheet_form.html        # Form tạo phiếu mới (Khu vực kéo thả file scan)
│   ├── sheet_detail.html      # Màn hình Split-View (Bên trái: PDF Viewer, Bên phải: Form Data)
│   ├── _sign_modal.html       # (Partial) Modal hiển thị trạng thái đang gọi API Ký số
│   └── sheet_review.html      # Màn hình dành cho VTC/Vận hành phê duyệt
│
└── checks/
    ├── check_list.html        # Lịch sử kiểm tra
    └── check_form.html        # Form dạng Lưới (Grid) để nhập dữ liệu đo đạc thực tế
```

## 3. Thiết kế Bố cục Chính (Layout - `base.html`)

Giao diện hỗ trợ Dark Mode, phong cách Sleek Design.

- **Sidebar (Trái - 250px):** 
  - Hiển thị logo EVN/RMS.
  - Menu điều hướng: Dashboard, Trạm Biến áp, Phiếu Chỉnh định, Biên bản Kiểm tra, Quản trị hệ thống.
- **Header (Trên):**
  - Thanh tìm kiếm toàn cục (Global Search).
  - Tên người dùng đang đăng nhập & Nút chuyển đổi Dark/Light mode.
  - Dropdown Đăng xuất.
- **Content Area (Giữa):** Hiển thị khối nội dung chính.

## 4. UI Đặc thù: Màn hình Chi tiết Phiếu Chỉnh định (Split-View)
Đây là màn hình quan trọng nhất của hệ thống, đòi hỏi UX tốt để rà soát.

Sử dụng cấu trúc Flexbox hoặc CSS Grid chia đôi màn hình:
- **Cột Trái (60%):** Nhúng thẻ `<iframe src="{{ sheet.scan_file.url }}">` hoặc thư viện PDF.js để render file scan trực tiếp trên trình duyệt.
- **Cột Phải (40%):** 
  - Phía trên: Hiển thị các Metadata của Phiếu (Mã phiếu, Trạm, Rơ-le, Người phát hành).
  - Giữa: Box Trạng thái Chữ ký (Hiển thị list user đã ký số). Nút **"Ký Số EVN"** to, rõ ràng.
  - Dưới: Nơi nhập liệu Mock Data/Form hoặc hiển thị `extracted_data` dạng JSON cho Kỹ thuật viên đối chiếu.

### 4.1 Tích hợp Ký số không Refresh trang bằng HTMX
```html
<!-- Nút ký số dùng htmx để post ngầm -->
<button hx-post="{% url 'sheet_sign' sheet.id %}" 
        hx-target="#signature-status-box" 
        hx-swap="innerHTML"
        class="bg-blue-600 text-white px-4 py-2 rounded shadow">
    <i class="fas fa-file-signature"></i> Ký số & Phát hành
</button>

<div id="signature-status-box">
    <!-- Nơi hiển thị kết quả trả về từ View (ví dụ: Chữ ký thành công / Mở popup) -->
</div>
```

## 5. UI Đặc thù: Bảng nhập Liệu Định kỳ
- Tạo Table với Input ở mỗi dòng.
- Khi người dùng nhập số, sử dụng Alpine.js (chạy client-side) để tính toán màu sắc cảnh báo đỏ/xanh ngay lập tức trước khi bấm "Lưu".

```html
<tr x-data="{ measured: 0, standard: {{ item.standard_value }} }">
    <td>{{ item.parameter_name }}</td>
    <td>{{ item.standard_value }}</td>
    <td><input type="number" x-model="measured" name="measured_{{ item.code }}"></td>
    <td>
        <span x-text="Math.abs(measured - standard)" 
              :class="Math.abs(measured - standard) > 0.05 ? 'text-red-500' : 'text-green-500'">
        </span>
    </td>
</tr>
```
