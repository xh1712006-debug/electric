# Đặc tả Kiểm thử Dự án (Project Testing Specification)

Tài liệu này quy định chiến lược kiểm thử, cấu hình môi trường, và các quy tắc viết mã kiểm thử (testing) dành riêng cho dự án hiện tại.

## 1. Chiến lược Kiểm thử (Testing Strategy)
Hệ thống được đảm bảo chất lượng thông qua 3 lớp kiểm thử chính:

- **Kiểm thử Đơn vị (Unit Test)**:
  - Tập trung kiểm tra tính đúng đắn của các Service và Helper functions độc lập.
  - Sử dụng giả lập (Mocking) để cô lập dữ liệu.
- **Kiểm thử Tích hợp (Integration Test)**:
  - Kiểm tra luồng gọi API đầu cuối (End-to-End API testing) kết nối giữa Router -> Middleware -> Controller -> Database.
  - Sử dụng cơ sở dữ liệu kiểm thử (Test DB) riêng biệt để đảm bảo không ghi đè dữ liệu thật.
- **Kiểm thử Giao diện (E2E UI Test)**:
  - Kiểm tra các luồng người dùng trên trình duyệt (ví dụ: luồng Đăng nhập, luồng Đặt hàng).

## 2. Công cụ Sử dụng (Testing Stack)
- **Kiểm thử Backend**: `Jest` phối hợp với `Supertest` để giả lập các HTTP request.
- **Kiểm thử Giao diện Frontend**: `Vitest` và `React Testing Library` (hoặc `Playwright` cho E2E).

## 3. Quy chuẩn Đặt tên & Viết Test (Convention)
- **Đường dẫn file test**:
  - Unit tests đặt cạnh file code chính hoặc đặt trong thư mục `tests/unit/` (ví dụ: `auth.controller.unit.test.js`).
- **Đặt tên ca kiểm thử**:
  - Sử dụng từ khóa `describe` để gom nhóm tính năng và `it` hoặc `test` để định nghĩa kịch bản.
  - Tên testcase nên viết rõ ràng (ví dụ: `should return 400 if email is missing`).

### Ví dụ mã nguồn kiểm thử (Jest):
```javascript
describe('Auth Service - Register', () => {
  it('should hash the password before saving to database', async () => {
    const userData = { email: 'test@example.com', password: 'password123' };
    const savedUser = await authService.register(userData);
    
    expect(savedUser.password).not.toBe(userData.password);
    expect(savedUser.password).toHaveLength(60); // Độ dài bcrypt hash
  });
});
```

## 4. Lệnh chạy & Độ phủ (Execution & Coverage)
- **Lệnh chạy toàn bộ test**: `npm run test` (hoặc lệnh cấu hình tương ứng).
- **Lệnh chạy kiểm tra độ phủ**: `npm run test:coverage` (được cấu hình xuất báo cáo ra thư mục `coverage/`).
- **Tiêu chuẩn độ phủ tối thiểu (Minimum Coverage Gates)**:
  - Statements (Độ phủ dòng code): **> 85%**
  - Branches (Độ phủ rẽ nhánh logic): **> 80%**
  - Functions (Độ phủ hàm): **> 90%**
