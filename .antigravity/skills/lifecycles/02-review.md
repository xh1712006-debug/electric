# Kỹ năng Đánh giá mã nguồn (Review Skill)

Tài liệu này quy định quy trình tự rà soát (Self-review) và chuẩn bị mã nguồn để lập trình viên đánh giá trước khi tiến hành bước tiếp theo.

## 1. Quy trình Tự Đánh giá (Self-Review Checklist)
Trước khi bàn giao hoặc đẩy mã nguồn lên hệ thống, Agent bắt buộc phải kiểm tra lại các yếu tố sau:

- **Tính Đúng đắn và Logic**:
  - Mã nguồn có giải quyết triệt để yêu cầu nghiệp vụ trong `PROJECT_REQUIREMENTS.md` không?
  - Có các trường hợp biên (edge cases) hoặc lỗi tiềm ẩn nào chưa được xử lý không?
- **Chất lượng và Định dạng Code**:
  - Không còn các đoạn mã thử nghiệm, `console.log` dư thừa, hoặc các đoạn code bị comment vô nghĩa.
  - Định dạng mã nguồn nhất quán (thụt dòng, khoảng trắng, dấu ngoặc).
- **Chú thích (Comments) & Tài liệu**:
  - Tất cả chú thích mới và sửa đổi phải sử dụng **Tiếng Việt** chuẩn mực, ngắn gọn.
  - Các hàm phức tạp hoặc các quyết định thiết kế quan trọng phải có giải thích đi kèm.
  - **Chuẩn bị Đồng bộ Đặc tả**: Rà soát các thay đổi thực tế trong mã nguồn và chuẩn bị danh sách các tài liệu đặc tả sẽ cần được cập nhật (ví dụ: DB schema, endpoint mới). Việc ghi nhận cập nhật vào các file tài liệu đặc tả chỉ được thực hiện sau khi code vượt qua kiểm thử ở bước Test.
- **Bảo mật & Hiệu năng**:
  - Đảm bảo không lưu các thông tin nhạy cảm (mật khẩu, API key, token) trực tiếp trong code (hardcoded secrets).
  - Tránh các lỗi hiệu năng như vòng lặp lồng nhau không tối ưu hoặc truy vấn dữ liệu thừa.

## 2. Giao tiếp và Tương tác (Human-in-the-Loop)
- **Báo cáo sự thay đổi**: Cung cấp một tóm tắt ngắn gọn nhưng đầy đủ về các sửa đổi lớn, các quyết định kiến trúc đã đưa ra và lý do đằng sau chúng.
- **Tiếp nhận phản hồi**: Luôn sẵn sàng giải thích và điều chỉnh mã nguồn khi lập trình viên đưa ra ý kiến phản hồi hoặc yêu cầu sửa đổi. Không tự ý bỏ qua các ý kiến đóng góp của người dùng.
- **Tạo Walkthrough**: Cập nhật hoặc tạo file `walkthrough.md` trong thư mục báo cáo để ghi nhận kết quả rà soát chi tiết.
