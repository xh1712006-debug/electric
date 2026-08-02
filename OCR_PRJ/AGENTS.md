# AGENTS.md

Khuôn khổ dự án (Project harness) dành cho việc phát triển với sự hỗ trợ của Agent một cách đáng tin cậy.

## Quy trình khởi động

Trước khi viết code:

1. **Xác nhận thư mục làm việc** bằng lệnh `pwd`
2. **Đọc toàn bộ file này**
3. **Đọc toàn bộ file `immediate.md`** để xác định tác vụ hiện tại, tác vụ tiếp theo, các yếu tố gây cản trở (blockers), các bài test yêu cầu và Bằng chứng nghiệm thu (Acceptance Evidence)
4. **Đọc các tài liệu dự án và tính liên tục** (`PROGRESS.md`, `plan.md`, `docs/ARCHITECTURE.md`, `docs/PRODUCT.md`, README, hoặc các tài liệu tương đương nếu có)
5. **Chạy lệnh xác minh tiêu chuẩn (standard verification command)** để xác nhận môi trường đang hoạt động tốt
6. **Đọc file `feature_list.json`** để xem trạng thái tính năng hiện tại
7. **Xem xét trạng thái repository** bằng `git status --short` và `git log --oneline -5`
8. **Thực hiện bắt buộc Cổng xác nhận tác vụ ngay lập tức (Immediate Task Confirmation Gate) dưới đây** trước khi triển khai hoặc thực hiện bất kỳ thay đổi nào đối với dự án

Nếu quá trình xác minh cơ sở (baseline verification) thất bại, hãy bao gồm thông báo lỗi và đề xuất sửa chữa trong phần xác nhận. Cần sửa chữa cơ sở trước khi thêm phạm vi mới, nhưng không được thay đổi repository cho đến khi người dùng xác nhận phương pháp sửa chữa.

## Cổng xác nhận tác vụ ngay lập tức (Bắt buộc)

Bắt đầu mỗi phiên làm việc, sau khi đọc `immediate.md` và hoàn thành các bước kiểm tra (chỉ đọc) lúc khởi động, Agent phải tạm dừng và xác nhận tác vụ tiếp theo với người dùng trước khi tiến hành triển khai.

Nội dung xác nhận phải nêu rõ ràng tất cả các thông tin sau:

1. **Tác vụ tiếp theo (Next task)**: ID tác vụ, tiêu đề, trạng thái hiện tại, và lý do tại sao đây là tác vụ tiếp theo phù hợp dựa trên `immediate.md`.
2. **Kết quả dự kiến (Planned outcome)**: hành vi cụ thể hoặc artifact sẽ tồn tại khi tác vụ hoàn thành.
3. **Cách tiếp cận triển khai (Implementation approach)**: các bước chính, các file/thành phần dự kiến thay đổi và các ranh giới quan trọng cần được giữ nguyên.
4. **Kế hoạch xác minh (Verification plan)**: chính xác các bài kiểm thử Unit, Integration, E2E, Platform, Contract, Security hoặc các bài kiểm thử khác sẽ được chạy cho tác vụ này.
5. **Bằng chứng nghiệm thu (Acceptance Evidence)**: Bằng chứng nào sẽ được ghi nhận để chứng minh trạng thái đã hoàn thành, hoàn thành một phần hoặc thất bại.
6. **Các quyết định yêu cầu sự can thiệp của con người (Human decisions required)**: mọi sự lựa chọn chưa được giải quyết về sản phẩm, cấu trúc (schema), kiến trúc, môi trường, bảo mật, hoặc tính tương thích mà người dùng phải xác nhận.
7. **Trợ giúp từ con người hoặc đầu vào cần thiết (Human help or inputs required)**: các file PDF mẫu, đầu ra dự kiến, ngôn ngữ/runtime của consumer, các thư mục input/output cho phép, thông tin xác thực, quyền truy cập máy, review thủ công hoặc bất kỳ điều kiện tiên quyết nào người dùng phải cung cấp.
8. **Rủi ro và cản trở (Risks and blockers)**: các rủi ro, sự không chắc chắn, thiếu dependency, giới hạn của test hoặc tác động tới các hành vi hiện hành đã biết.

Nếu không yêu cầu quyết định hoặc trợ giúp từ con người, hãy nói rõ. Tuyệt đối không được tự ý ngầm hiểu rằng đầu vào của con người là không cần thiết.

Kết thúc phần xác nhận bằng cách hỏi người dùng xem có tiến hành tác vụ và phương pháp tiếp cận đã đề xuất hay không. Không bắt đầu triển khai cho đến khi người dùng xác nhận. Việc kiểm tra (chỉ đọc) và xác minh cơ sở được cho phép trước khi có sự xác nhận; nhưng không được thay đổi code, schema, tracker, dependency, môi trường và sinh các file artifacts.

Nếu tin nhắn mở đầu của người dùng đã yêu cầu một tác vụ cụ thể, vẫn phải so sánh nó với `immediate.md`, giải thích bất kỳ sự xung đột nào về thứ tự/sự phụ thuộc, liệt kê các quyết định hoặc đầu vào cần thiết từ con người, và yêu cầu xác nhận trước khi triển khai.

Nếu `immediate.md` bị thiếu, không nhất quán bên trong, không có tác vụ tiếp theo có thể xác định, hoặc xung đột nghiêm trọng với trạng thái repository, hãy dừng lại sau khi kiểm tra bằng việc chỉ đọc và hỏi người dùng cách giải quyết. Không tự bịa ra hoặc ngầm thay đổi thứ tự kế hoạch tức thời.

## Quy tắc làm việc

- **Kế hoạch tức thời (Immediate plan) là bắt buộc**: Sử dụng `immediate.md` làm thứ tự thực thi và nguồn trạng thái cho công việc tích hợp trên cùng server (same-server integration)
- **Mỗi lần một tác vụ**: Chỉ làm việc trên chính xác một tác vụ `IMMEDIATE-*` đã được xác nhận mỗi phiên trừ khi người dùng yêu cầu thay đổi phạm vi một cách rõ ràng
- **Mỗi lần một tính năng**: Đảm bảo tác vụ đã được xác nhận ánh xạ tới chính xác một tính năng chưa hoàn thành trong `feature_list.json`
- **Không tự ý chuyển đổi tác vụ**: Nếu tác vụ đã được xác nhận bị cản trở/chặn lại, hãy báo cáo yếu tố cản trở và xin chỉ thị trước khi bắt đầu một tác vụ khác
- **Bắt buộc xác minh (Verification required)**: Không đánh dấu là 'done' mà không chạy các lệnh xác minh
- **Cập nhật artifacts**: Trước khi kết thúc phiên làm việc, hãy cập nhật `immediate.md`, `PROGRESS.md`, và `feature_list.json`
- **Làm việc đúng phạm vi (Stay in scope)**: Không sửa đổi các file không liên quan đến tính năng hiện tại
- **Giữ trạng thái sạch sẽ (Leave clean state)**: Phiên làm việc tiếp theo phải có thể chạy lệnh xác minh tiêu chuẩn `init.ps1` ngay lập tức

## Các Artifacts Yêu cầu

- `immediate.md` — Thứ tự tác vụ tích hợp same-server, trạng thái trực tiếp, tests, cản trở (blockers), và Bằng chứng nghiệm thu
- `plan.md` — Kế hoạch cải thiện dài hạn; nó không thay thế tác vụ tức thời hiện tại trừ khi có sự xác nhận của người dùng
- `feature_list.json` — Trình theo dõi trạng thái tính năng (nguồn chân lý - source of truth)
- `PROGRESS.md` — Nhật ký tính liên tục của phiên làm việc
- `init.ps1` — Đường dẫn xác minh và khởi động tiêu chuẩn trên kho lưu trữ Windows này
- `session-handoff.md` — Tùy chọn, dành cho các phiên lớn/dài hơn

## Định nghĩa Hoàn thành (Definition of Done)

Một tính năng chỉ được xem là hoàn thành khi TẤT CẢ các điều kiện sau là đúng (true):

- [ ] Hành vi mục tiêu được triển khai
- [ ] Mọi test yêu cầu bởi tác vụ `IMMEDIATE-*` đã được xác nhận đều thực sự được chạy, hoặc bất kỳ test nào không có sẵn đều được ghi nhận rõ ràng là blocker
- [ ] Bằng chứng nghiệm thu và trạng thái tác vụ cuối cùng được ghi vào `immediate.md`
- [ ] Bằng chứng được đồng bộ vào `feature_list.json` và `PROGRESS.md`
- [ ] Repository có thể được khởi động lại thông qua lộ trình khởi động tiêu chuẩn

## Kết thúc Phiên

Trước khi kết thúc một phiên làm việc:

1. Cập nhật trạng thái tác vụ đã xác nhận và Bằng chứng nghiệm thu vào `immediate.md`
2. Cập nhật các trường tổng quan trong `immediate.md`: tác vụ hiện tại, tác vụ tiếp theo, và blockers
3. Cập nhật `PROGRESS.md` với trạng thái hiện tại và kết quả xác minh chính xác
4. Cập nhật `feature_list.json` với trạng thái tính năng/bằng chứng đã được đồng bộ
5. Ghi nhận mọi rủi ro chưa được giải quyết, test không có sẵn, hành động của con người hoặc blockers
6. Commit với thông báo mô tả rõ ràng một khi công việc đang ở trạng thái an toàn
7. Giữ repository sạch sẽ để phiên làm việc tiếp theo có thể chạy lệnh xác minh tiêu chuẩn ngay lập tức

## Lệnh xác minh

```bash
# Xác minh đầy đủ (khuyên dùng)
powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1
```

Các bước kiểm tra bắt buộc:
- Việc khám phá/chạy kiểm thử unit/regression của Python được thực thi bởi `init.ps1`
- Mọi test bổ sung được yêu cầu bởi tác vụ `IMMEDIATE-*` đã xác nhận

## Leo thang (Escalation)

Nếu bạn gặp phải:
- **Quyết định về kiến trúc**: Tham khảo tài liệu kiến trúc dự án nếu có, nếu không thì hỏi người dùng
- **Yêu cầu không rõ ràng**: Kiểm tra tài liệu về yêu cầu/sản phẩm nếu có, nếu không thì hỏi người dùng
- **Lỗi kiểm thử (test) lặp đi lặp lại**: Cập nhật tiến trình, đánh dấu cờ cần con người review
- **Mơ hồ về phạm vi**: Hãy đọc lại `immediate.md` trước tiên, sau đó là `feature_list.json`, và hỏi người dùng nếu vẫn còn sự mơ hồ
- **Thiếu đầu vào của con người**: Đánh dấu tác vụ tức thời hiện tại là 'bị chặn (blocked)' hoặc 'hoàn thành một phần (partially complete)' kèm theo chính xác những đầu vào đang thiếu; tuyệt đối không ngầm tự động chuyển đổi tác vụ
