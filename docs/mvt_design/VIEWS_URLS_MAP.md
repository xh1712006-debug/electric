# Thiết kế Routing và Views (MVT)

Thay vì thiết kế các API Endpoint trả về JSON (như DRF), hệ thống sẽ sử dụng các `urls.py` và `views.py` để lấy dữ liệu từ DB (thông qua Djongo ORM), gán vào Context và trả về mã HTML render từ Template.

## 1. Cấu trúc URL Định tuyến (`urls.py`)

| URL Pattern | Tên (Name) | Phương thức HTTP | Chức năng (Ý nghĩa) |
|---|---|---|---|
| `/` | `home` | GET | Trang Dashboard chính (Thống kê phiếu). |
| `/auth/login/` | `login` | GET, POST | Trang Đăng nhập hệ thống. |
| `/auth/logout/` | `logout` | POST | Đăng xuất. |
| `/stations/` | `station_list` | GET | Danh sách Trạm biến áp. |
| `/stations/<id>/` | `station_detail` | GET | Chi tiết Trạm (gồm danh sách Ngăn lộ, Rơ-le). |
| `/stations/import/` | `station_import` | GET, POST | Upload file JSON/Excel khởi tạo Cấu trúc Trạm. |
| `/sheets/` | `sheet_list` | GET | Danh sách Phiếu Chỉnh định. |
| `/sheets/new/` | `sheet_create` | GET, POST | Tạo phiếu mới & Upload file bản scan. |
| `/sheets/<id>/` | `sheet_detail` | GET | Xem chi tiết thông số phiếu & File PDF. |
| `/sheets/<id>/sign/` | `sheet_sign` | POST | Khởi tạo luồng Ký số EVN cho người dùng hiện tại. |
| `/sheets/<id>/review/` | `sheet_review` | GET, POST | VTC/Điều độ rà soát và phê duyệt phiếu. |
| `/sheets/<id>/transfer/`| `sheet_transfer`| POST | Chuyển giao phiếu cho Kỹ thuật viên (Giao việc). |
| `/checks/` | `check_list` | GET | Danh sách các biên bản kiểm tra định kỳ. |
| `/checks/new/<relay_id>/`| `check_create` | GET, POST | Form điền số liệu kiểm tra định kỳ rơ-le thực tế. |

## 2. Đặc tả Logic của Views (`views.py`)

Sử dụng kết hợp Class-Based Views (CBV) và Function-Based Views (FBV) theo chuẩn Django:

### 2.1 View Tạo Phiếu & Upload Bản Scan (`sheet_create`)
- **GET:** Trả về Template `sheets/sheet_form.html` kèm ModelForm của `SettingSheet`.
- **POST:** Nhận `scan_file` và `title`.
  - Validate file upload (đảm bảo là PDF/JPG hợp lệ, kích thước < 10MB).
  - Lưu vào MongoDB (file được lưu trên storage vật lý, đường dẫn lưu vào Mongo).
  - Trạng thái phiếu thiết lập ban đầu: `DRAFT`.
  - Redirect về `sheet_detail`.

### 2.2 View Khởi tạo Ký số (`sheet_sign`)
Đây là View thực hiện tích hợp API bên ngoài (Hệ thống Ký số EVN).
- **POST:** 
  1. Lấy `SettingSheet` từ Database.
  2. Hash nội dung file scan (`hash_sha256`).
  3. Gửi HTTP Request (bằng thư viện `requests`) sang `https://evn-sign-api/initiate/` kèm theo hash và User ID hiện tại.
  4. Lấy lại `session_id` và `signing_url` từ EVN.
  5. Trả về Template hoặc dùng HTMX trigger để mở `signing_url` dạng popup/iframe cho user ký.
  6. (Sau khi user ký xong) Hệ thống EVN callback hoặc View tự gọi lại EVN để lấy `signature_data` (Base64) -> Nhúng data vào `SettingSheet.signatures` (Mảng). Đổi trạng thái phiếu.

### 2.3 View Nhập liệu Kiểm tra Định kỳ (`check_create`)
Do MongoDB lưu toàn bộ thông số Rơ-le dạng Array trong DB, việc xuất form cực kỳ dễ dàng.
- **GET:** Lấy `Relay.settings`. Build một danh sách các field để render HTML dạng lưới (Grid/Table). 
- **POST:** Nhận cục `POST.dict()` từ Form.
  - Lặp qua danh sách thông số, so sánh `measured_value` với `standard_value` có sẵn trong Rơ-le (MongoDB Document).
  - Tính toán `deviation_percent = abs(do - chuan)/chuan * 100`.
  - Kiểm tra có nằm trong giới hạn (`tolerance_min` - `tolerance_max`) không.
  - Đóng gói toàn bộ kết quả vào một Array nhúng lưu vào Model `PeriodicCheck.items`.
  - Render ra template báo cáo (`checks/check_report.html`) cảnh báo Đỏ/Xanh.

## 3. Quản lý Permission tại Views
Sử dụng Mixins để chặn quyền truy cập (RBAC).

```python
from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import DetailView

class SheetReviewView(UserPassesTestMixin, DetailView):
    model = SettingSheet
    template_name = "sheets/sheet_review.html"

    # Chỉ VTC, Vận Hành, Điều độ mới được phép Rà soát
    def test_func(self):
        user = self.request.user
        return user.groups.filter(name__in=['VTC', 'OPERATION_UNIT', 'DISPATCHER']).exists()
```
