# Hướng dẫn Phát triển cho Antigravity AI

## Triết lý Cốt lõi**Yêu cầu là số 1**: Luôn đối chiếu với [PROJECT_REQUIREMENTS.md](file:///PROJECT_REQUIREMENTS.md) để đảm bảo đi đúng hướng nghiệp vụ.

- **Kiến trúc đồng nhất**: Tuân thủ thiết kế kỹ thuật Modular MVC trong [docs/cores/02-backend.md](file:///docs/cores/02-backend.md).
- **Code sạch**: Viết mã nguồn dễ bảo trì và có cấu trúc rõ ràng.

## Quy tắc & Tiêu chuẩn Dự án

- **Tài liệu chi tiết**: Các hướng dẫn sâu hơn được lưu trong thư mục `docs/`.
- **Luật riêng cho Agent**: Các quy định cụ thể về code style, đặt tên... nằm tại `.antigravity/rules/`.
- **Quy tắc quan trọng nhất**: Luôn viết chú thích (comment) bằng **tiếng Việt**, ngắn gọn. Xem chi tiết tại [comment.md](file:///.antigravity/rules/comment.md)

## Kỹ năng & Lệnh (Skills & Commands)

- **Quy trình Phát triển**: Luôn tuân thủ quy trình 4 bước **Generate - Review - Test - Push** được định nghĩa tại [workflow.md](file:///.antigravity/skills/workflow.md). Xem chi tiết từng kỹ năng:
  - [Generate Skill (Tạo mã)](file:///.antigravity/skills/lifecycles/01-generate.md)
  - [Review Skill (Rà soát)](file:///.antigravity/skills/lifecycles/02-review.md)
  - [Test Skill (Kiểm thử)](file:///.antigravity/skills/lifecycles/03-test.md)
  - [Push Skill (Đẩy code)](file:///.antigravity/skills/lifecycles/04-push.md)
- Tham khảo thư mục `.antigravity/skills` để sử dụng các kỹ năng và luồng công việc (workflow) nâng cao.
