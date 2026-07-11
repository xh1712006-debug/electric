# Quy trình Triển khai & Vận hành (Deployment & Operations Guide)

Tài liệu này đặc tả quy trình đưa mã nguồn ứng dụng lên môi trường Production, cấu hình biến môi trường, và các công cụ giám sát vận hành.

## 1. Môi trường Máy chủ & Hạ tầng (Infrastructure Stack)
- **Môi trường**: AWS / Google Cloud / VPS Linux (Ubuntu Server).
- **Cách thức đóng gói**: `Docker` & `Docker Compose` (khuyên dùng để đồng bộ môi trường phát triển và môi trường chạy thật).
- **Web Server**: `Nginx` đóng vai trò Reverse Proxy và SSL Termination (Let's Encrypt).

---

## 2. Quản lý Biến Môi trường (Environment Variables)
Biến môi trường được lưu tại tệp `.env` ở máy chủ chạy thật. Tuyệt đối không commit giá trị nhạy cảm lên GitHub.

| Tên biến (Key) | Mô tả (Description) | Ví dụ (Example Value) |
| :--- | :--- | :--- |
| `PORT` | Cổng mạng chạy ứng dụng | `3000` |
| `NODE_ENV` | Môi trường thực thi ứng dụng | `production` |
| `DATABASE_URL` | Chuỗi kết nối Cơ sở dữ liệu | `postgresql://user:pass@host:5432/db` |
| `JWT_SECRET` | Khóa bí mật dùng để ký token | `super-secret-key-do-not-share` |

---

## 3. Quy trình CI/CD (GitHub Actions / GitLab CI)
Quy trình tích hợp và triển khai tự động diễn ra sau mỗi hành động Merge vào nhánh `main`:

```mermaid
graph LR
    A[Code Push/Merge] --> B(1. Lint & Build Check)
    B --> C(2. Run Jest Tests)
    C --> D(3. Docker Build & Push)
    D --> E(4. Deploy to Server)
```

### Các bước trong file `.github/workflows/deploy.yml` mẫu:
1. **Kiểm tra cú pháp (Linting)**: Đảm bảo code sạch, không lỗi format.
2. **Chạy kiểm thử (Testing)**: Toàn bộ Unit và Integration Test phải pass 100%.
3. **Build Docker Image**: Đóng gói ứng dụng thành Image mới và đẩy lên Registry (Docker Hub / AWS ECR).
4. **Deploy**: SSH vào Server, thực hiện pull image mới nhất về và restart service (`docker-compose up -d --build`).

---

## 4. Giám sát & Nhật ký (Monitoring & Logging)
- **Ghi log (Logging)**: Sử dụng các thư viện ghi log có cấu trúc như `Winston` hoặc `Pino` xuất log dạng JSON để dễ lọc.
- **Giám sát hiệu suất (APM)**: Sử dụng Prometheus + Grafana hoặc Datadog để giám sát CPU, RAM, thời gian phản hồi API.
- **Quản lý Process**: Sử dụng `PM2` đối với các dự án Node.js không dùng Docker để đảm bảo tự khởi động lại khi ứng dụng bị sập.
