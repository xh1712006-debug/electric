# Kỹ năng Kiểm thử (Test Skill)

Tài liệu này định nghĩa quy chuẩn viết và chạy kiểm thử (Testing) để đảm bảo chất lượng, tính ổn định và độ tin cậy của mã nguồn trước khi tích hợp vào nhánh chính.

## 1. Viết Ca Kiểm thử (Writing Tests)
Mọi tính năng mới hoặc bản vá lỗi phải đi kèm với các ca kiểm thử tương ứng:
- **Kiểm thử Đơn vị (Unit Test)**: Viết các ca kiểm thử tập trung vào logic của từng hàm, từng lớp độc lập.
- **Bao phủ kịch bản**:
  - **Happy Path**: Luồng chạy bình thường khi dữ liệu đầu vào hợp lệ.
  - **Sad Path**: Luồng xử lý lỗi khi dữ liệu đầu vào không hợp lệ hoặc hệ thống gặp sự cố.
- **Cô lập kiểm thử (Mocking)**: Sử dụng cơ chế giả lập (Mocking) cho các phụ thuộc bên ngoài như cơ sở dữ liệu, API bên thứ ba, dịch vụ gửi mail, v.v., để đảm bảo bộ test chạy nhanh và ổn định.

## 2. Thực thi Kiểm thử (Running Tests)
- **Chạy bộ kiểm thử**: Sử dụng lệnh kiểm thử của dự án (ví dụ: `npm run test` hoặc lệnh tương đương) để chạy toàn bộ các ca kiểm thử.
- **Tiêu chuẩn vượt qua**: Tất cả các ca kiểm thử bắt buộc phải đạt **100% thành công (PASS)**. Không chấp nhận bất kỳ ca test nào bị lỗi hoặc bị bỏ qua mà không có lý do chính đáng.
- **Quy trình Sửa lỗi (Debugging Workflow)**:
  - Nếu có ca test thất bại, Agent phải phân tích thông báo lỗi (log) để định vị nguyên nhân.
  - Tiến hành sửa đổi mã nguồn tại bước **Generate** và chạy lại toàn bộ bộ kiểm thử cho đến khi tất cả các ca đều thành công.

## 3. Xác minh Thủ công (Manual Verification)
- Trong trường hợp tính năng liên quan đến giao diện người dùng (UI) hoặc luồng tích hợp phức tạp chưa thể tự động hóa hoàn toàn, Agent phải mô tả rõ kịch bản xác minh thủ công trong file `walkthrough.md` hoặc cung cấp ảnh chụp/quay màn hình chứng minh tính năng hoạt động đúng.
