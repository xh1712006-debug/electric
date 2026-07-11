# Thiết kế Xác thực & Bảo mật (Authentication & Security Design)

Tài liệu này đặc tả các cơ chế xác thực, phân quyền và bảo mật dữ liệu toàn bộ hệ thống để bảo vệ trước các mối đe dọa.

## 1. Cơ chế Xác thực (Authentication)
Hệ thống sử dụng cơ chế xác thực bằng mã thông báo **JSON Web Token (JWT)**:

### Luồng đăng nhập (Authentication Flow):
1. Client gửi email/password qua API `POST /api/v1/auth/login`.
2. Server xác thực thông tin, nếu đúng sẽ trả về bộ đôi mã thông báo:
   - `AccessToken`: Thời hạn ngắn (ví dụ: 15 phút), dùng để gọi các API.
   - `RefreshToken`: Thời hạn dài (ví dụ: 7 ngày), lưu trữ ở cơ sở dữ liệu để cấp lại AccessToken mới.
3. Client lưu trữ `AccessToken` trong bộ nhớ RAM của ứng dụng và `RefreshToken` trong `HttpOnly Secure Cookie` để ngăn chặn tấn công XSS.

---

## 2. Phân quyền Người dùng (Authorization & RBAC)
Hệ thống quản lý quyền truy cập dựa trên mô hình **Role-Based Access Control (RBAC)** phối hợp với các quyền chi tiết (Permissions):

- **Vai trò (Roles)**: `ADMIN`, `MANAGER`, `USER`.
- **Quyền hạn (Permissions)**:
  - `user.manage`: Quyền thêm/sửa/xóa người dùng.
  - `data.read`: Quyền đọc dữ liệu nghiệp vụ.
  - `data.write`: Quyền ghi/sửa dữ liệu nghiệp vụ.

### Middleware kiểm tra quyền truy cập (API Level):
Trước khi vào Controller xử lý logic, request phải đi qua hai lớp bảo vệ:
1. `requireToken`: Xác định danh tính người dùng từ AccessToken.
2. `checkPermission('data.write')`: Kiểm tra xem vai trò của người dùng có quyền tương ứng hay không.

---

## 3. Bảo vệ Dữ liệu & Phòng chống Tấn công
Để hạn chế tối đa các lỗ hổng theo chuẩn OWASP Top 10, dự án phải tuân thủ nghiêm ngặt các quy tắc:

- **Băm mật khẩu (Password Hashing)**: Luôn sử dụng thư viện `bcrypt` (hoặc `argon2`) với hệ số salt thích hợp để băm mật khẩu trước khi ghi vào cơ sở dữ liệu.
- **Phòng chống SQL Injection**: Sử dụng các thư viện ORM hỗ trợ chuẩn hóa câu truy vấn (Parameterized queries), tuyệt đối không ghép chuỗi SQL thủ công.
- **Cấu hình CORS (Cross-Origin Resource Sharing)**: Chỉ cho phép các tên miền (domain) cụ thể truy cập API, không để cấu hình `Access-Control-Allow-Origin: *` trên môi trường Production.
- **Bảo vệ chống XSS (Cross-Site Scripting)**: Lọc sạch và loại bỏ mã độc (sanitize) trong toàn bộ dữ liệu đầu vào nhận được từ client.
