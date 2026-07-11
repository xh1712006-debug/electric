# Kỹ năng Tạo mã nguồn (Generate Skill)

Tài liệu này định nghĩa tiêu chuẩn và quy trình cho bước **Generate** (Tạo mã nguồn) trong dự án. Kỹ năng này hướng dẫn Agent phân tích, thiết lập kế hoạch và sinh mã nguồn chất lượng cao.

## 1. Nghiên cứu & Lập kế hoạch (Planning)
Trước khi viết hoặc sửa đổi bất kỳ mã nguồn nào, Agent phải:
- **Đọc kỹ yêu cầu**: Đối chiếu trực tiếp với tệp `PROJECT_REQUIREMENTS.md` để nắm bắt nghiệp vụ cốt lõi.
- **Khảo sát hệ thống**: Tìm kiếm cấu trúc hiện tại, các hàm tiện ích có sẵn để tái sử dụng, tránh viết lại logic.
- **Ghi nhận Đặc tả thiếu**: Nếu phát hiện tài liệu đặc tả ban đầu (`docs/cores/` hoặc `docs/features/`) bị thiếu hoặc lệch pha với nghiệp vụ thực tế, hãy ghi chú lại thông tin để chuẩn bị cập nhật đồng bộ sau khi code đã được kiểm thử chạy ổn định (tránh sửa đổi trực tiếp tài liệu đặc tả chính thức ở bước này).
- **Xác định phạm vi ảnh hưởng**: Ước lượng những tệp tin sẽ bị sửa đổi hoặc tạo mới.
- **Lập kế hoạch triển khai**: Đối với các thay đổi phức tạp, phải tạo hoặc cập nhật tệp `implementation_plan.md` và xin ý kiến phê duyệt của lập trình viên trước khi bắt đầu code.

## 2. Quy tắc Viết mã (Coding Guidelines)
Khi thực hiện bước Generate, mã nguồn phải tuân thủ các chuẩn mực sau:
- **Ngôn ngữ lập trình**:
  - Mã nguồn (biến, hàm, lớp, module, API): Sử dụng hoàn toàn bằng **Tiếng Anh** để đảm bảo tính chuyên nghiệp và chuẩn quốc tế.
  - Chú thích (Comments) & Giải thích: Sử dụng hoàn toàn bằng **Tiếng Việt** ngắn gọn, súc tích (tuân thủ quy tắc tại `comment.md`). Tập trung vào lý do *"tại sao làm thế này"* thay vì *"làm cái gì"*.
- **Cấu trúc mã**:
  - Viết mã sạch (Clean Code), đơn nhiệm (Single Responsibility Principle).
  - Tránh viết các đoạn mã quá dài, nên tách thành các module nhỏ, hàm tiện ích (utils) riêng.
  - Sử dụng cơ chế xử lý lỗi (error handling) đầy đủ, trả về thông điệp lỗi rõ ràng.
- **Hạn chế Placeholders**:
  - Không viết code giả, code chờ hoặc các ghi chú dạng `// TODO: implement later`. Nếu cần, phải hoàn thiện logic hoặc cấu hình một cách hoàn chỉnh.

## 3. Theo dõi Tiến độ
- Sử dụng tệp `task.md` để theo dõi các đầu việc trong quá trình sinh mã. Đánh dấu `[/]` khi bắt đầu thực hiện và `[x]` khi hoàn thành một đầu việc sinh mã.
