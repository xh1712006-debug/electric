# Kỹ năng Đẩy mã nguồn (Push Skill)

Tài liệu này hướng dẫn quy trình dọn dẹp, đóng gói và thực hiện đẩy (push) mã nguồn lên kho lưu trữ trực tuyến (repository) một cách an toàn và chuyên nghiệp.

## 1. Dọn dẹp Dự án (Cleanup)
Trước khi tạo commit, Agent phải đảm bảo:
- **Loại bỏ file rác**: Xóa các file log tạm thời, file scratch không còn sử dụng hoặc các thư mục tạm ngoài ý muốn.
- **Kiểm tra `.gitignore`**: Đảm bảo các tệp tin nhạy cảm (như file `.env` chứa mật khẩu, API key) hoặc thư mục build cục bộ không bị vô tình theo dõi bởi git.

## 2. Quy chuẩn Commit (Conventional Commits & Staged Flags)
Thông điệp commit phải tuân thủ chuẩn Conventional Commits và bắt buộc viết bằng **Tiếng Anh**:
- **Cấu trúc**: `<type>(<scope>): <description>`
- **Các phân loại (Type) chính**:
  - `feat`: Thêm tính năng mới.
  - `fix`: Sửa lỗi.
  - `docs`: Cập nhật tài liệu.
  - `style`: Thay đổi định dạng code (không ảnh hưởng logic).
  - `refactor`: Tái cấu trúc mã nguồn.
  - `test`: Thêm/sửa bộ kiểm thử.
  - `chore`: Thay đổi cấu hình build, dependency.
- **Tiêu chuẩn ngôn ngữ**: Toàn bộ thông điệp commit (tiêu đề và chi tiết) phải viết bằng **Tiếng Anh** ngắn gọn, súc tích.
- **Quy tắc cắm cờ (Double Commit Flags -m)**:
  - Chỉ sử dụng tối đa **2 cờ `-m`** để tạo thông điệp có cấu trúc sạch:
    - Cờ `-m` thứ nhất: Tiêu đề ngắn gọn (Title) tuân thủ chuẩn Conventional Commits.
    - Cờ `-m` thứ hai: Mô tả danh sách chi tiết các thay đổi (sử dụng dấu xuống dòng để viết các gạch đầu dòng).
  - Cú pháp: `git commit -m "type(scope): general short title in english" -m "- first change detail\n- second change detail"`

## 3. Tạo Pull Request & Đẩy code
- **Push lên nhánh tương ứng**: Đẩy các thay đổi lên nhánh tính năng (feature branch) hiện tại, tránh đẩy trực tiếp lên nhánh chính (`main`/`master`) trừ khi có yêu cầu cụ thể.
- **Tài liệu Walkthrough**: Tạo hoặc cập nhật tệp `walkthrough.md` làm báo cáo kỹ thuật của Agent (và bổ sung hướng dẫn sử dụng tính năng thực tế vào thư mục `docs/walkthroughs/` của dự án nếu cần) để tóm tắt các thay đổi đã thực hiện và kết quả kiểm thử thực tế làm minh chứng cho sự hoàn thành công việc.
