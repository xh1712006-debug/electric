# Thiết kế Kiến trúc Backend & API (Backend Architecture & API Design)

Tài liệu này đặc tả kiến trúc backend, cấu trúc thư mục mã nguồn và chuẩn giao tiếp API dành cho hệ thống.

## 1. Công nghệ Sử dụng (Backend Stack)
- **Runtime**: Node.js (phiên bản LTS) / Python / Go (chọn tùy dự án).
- **Framework**: Express.js / NestJS / FastAPI / Echo.
- **ORM / Query Builder**: Prisma / Sequelize / TypeORM / SQLAlchemy.

## 2. Cấu trúc Thư mục Mã nguồn theo mô hình Modular MVC (Directory Structure)
Hệ thống được thiết kế theo mô hình **Modular MVC**. Trong đó:
- **MVC Ngoài (Cơ sở/Root)**: Nằm trong thư mục `src/cores/`, định nghĩa các thành phần MVC dùng chung cho toàn bộ hệ thống (như Authentication, User profile, base middlewares, base models...).
- **MVC Trong (Module con)**: Nằm trong thư mục `src/modules/`, chia ứng dụng thành các phân hệ độc lập. Mỗi phân hệ (module) chứa một bộ MVC con khép kín tự quản lý logic của chính nó (ví dụ: module bài viết `posts`, module đặt hàng `orders`...).

Cấu trúc thư mục chi tiết như sau:

```text
📂 backend
 ┣ 📂 src
 ┃ ┣ 📂 cores                 # MVC ngoài dành cho root dùng chung cho cả hệ thống
 ┃ ┃ ┣ 📂 controllers         # Controllers dùng chung (ví dụ: Auth, Upload...)
 ┃ ┃ ┣ 📂 models              # Models cốt lõi / dùng chung (ví dụ: User, Session...)
 ┃ ┃ ┣ 📂 middlewares         # Middlewares hệ thống (requireToken, checkPermission...)
 ┃ ┃ ┗ 📜 cores.routes.js     # Router cốt lõi hệ thống
 ┃ ┣ 📂 modules               # Phân vùng chia theo các module độc lập
 ┃ ┃ ┣ 📂 post                # Module Bài viết (ví dụ)
 ┃ ┃ ┃ ┣ 📂 controllers       # Controller con của module Post
 ┃ ┃ ┃ ┣ 📂 models            # Model con của module Post
 ┃ ┃ ┃ ┣ 📂 services          # Lớp nghiệp vụ xử lý logic riêng của Post
 ┃ ┃ ┃ ┗ 📜 post.routes.js    # Routes con của module Post
 ┃ ┃ ┣ 📂 order               # Module Đơn hàng (ví dụ)
 ┃ ┃ ┃ ┣ 📂 controllers       # Controller con của module Order
 ┃ ┃ ┃ ┣ 📂 models            # Model con của module Order
 ┃ ┃ ┃ ┣ 📂 services          # Lớp nghiệp vụ xử lý logic riêng của Order
 ┃ ┃ ┃ ┗ 📜 order.routes.js   # Routes con của module Order
 ┃ ┃ ┗ 📂 ...                 # Các module nghiệp vụ khác
 ┃ ┣ 📂 utils                 # Các hàm helper dùng chung
 ┃ ┣ 📜 app.js                # Khởi tạo Express app và import các routes
 ┃ ┗ 📜 server.js             # Khởi chạy server lắng nghe kết nối
 ┗ 📜 package.json            # Định nghĩa các thư viện phụ thuộc
```


## 3. Quy chuẩn Thiết kế API (RESTful API Standards)

### Quy tắc đặt tên Endpoint:
- Sử dụng danh từ số nhiều cho các tài nguyên (ví dụ: `/api/v1/users`, `/api/v1/orders`).
- HTTP Methods:
  - `GET`: Lấy dữ liệu.
  - `POST`: Tạo mới tài nguyên.
  - `PUT`: Cập nhật toàn bộ tài nguyên.
  - `PATCH`: Cập nhật một phần tài nguyên.
  - `DELETE`: Xóa tài nguyên.

### Định dạng Dữ liệu phản hồi chuẩn (Response Format)

#### Phản hồi Thành công (Success Response):
```json
{
  "success": true,
  "message": "User updated successfully",
  "data": {
    "id": 1,
    "email": "user@example.com"
  }
}
```

#### Phản hồi Thất bại (Error Response):
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Email is already registered",
    "details": [
      {
        "field": "email",
        "issue": "must be a valid email format"
      }
    ]
  }
}
```

## 4. Đặc tả Chi tiết các Endpoint mẫu (Sample Endpoint Spec)

### 1. Đăng ký tài khoản mới
* **URL**: `/api/v1/auth/register`
* **Method**: `POST`
* **Request Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123",
    "full_name": "Nguyen Van A"
  }
  ```
* **Response (201 Created)**:
  ```json
  {
    "success": true,
    "message": "User registered successfully",
    "data": {
      "id": 12,
      "email": "user@example.com"
    }
  }
  ```
