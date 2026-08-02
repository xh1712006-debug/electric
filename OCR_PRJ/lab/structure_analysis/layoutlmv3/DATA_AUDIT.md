# Kiểm kê dữ liệu trước khi triển khai

Ngày kiểm kê: 2026-07-20.

## Kết quả kiểm kê ban đầu

- Kho có 20 ảnh trong `data/image`.
- Tên file và nội dung ảnh cho thấy toàn bộ các ảnh hiện có là trang 1. Các số như `_2`, `_3` trong tên file là biến thể tài liệu; số trang thực nằm ở hậu tố `page-001` hoặc `p1`.
- Chỉ tìm thấy một kết quả nhận dạng VietOCR đầy đủ được lưu đệm cho một ảnh trang 1.
- Có kết quả detection được lưu đệm cho 20 ảnh và có thể tái sử dụng bởi pipeline OCR hiện có.
- Không tìm thấy annotation BIO, ground truth phân loại vai trò, hoặc tập train/validation/test có thể dùng cho schema của thử nghiệm này.
- Môi trường lúc kiểm kê chưa cài `transformers`, `datasets`, `evaluate` hoặc `seqeval`; PyTorch hiện tại là bản CPU.

## Cập nhật sau khi bổ sung `data/image/page3`

- Đã phát hiện 19 ảnh trang 3 trong `data/image/page3`.
- Đã chạy suy luận trên đủ 19 ảnh bằng PP-OCR detector + VietOCR + LayoutLMv3 trên CPU.
- Kết quả kỹ thuật: 19 visualization, tổng thời gian LayoutLMv3 128,61 giây; toàn bộ 19 trang mất khoảng 1.270,92 giây do OCR live.
- Chưa có annotation hoàn chỉnh nên `ground_truth_available=false`, các chỉ số token/entity vẫn là `null`.
- Checkpoint FUNSD vẫn không tương thích schema relay; các nhãn `HEADER/QUESTION/ANSWER` không được đổi giả thành `PARAM_*`.

## Hệ quả

- Không thể fine-tune hoặc báo cáo precision/recall/F1 thật ở thời điểm hiện tại.
- Không dùng trang 1 để thay thế giả cho yêu cầu trang 3 trở đi.
- Chế độ kiểm kê/suy luận phải tạo kết quả rỗng có lý do rõ ràng khi không có trang đủ điều kiện.
- Pipeline fine-tuning được chuẩn bị đầy đủ, nhưng chỉ cho phép chạy sau khi annotation thật có trạng thái `completed` và vượt qua kiểm tra schema.
- Checkpoint FUNSD cộng đồng, nếu dùng để kiểm tra kỹ thuật, có hệ nhãn khác schema mục tiêu; nhãn đó phải được giữ nguyên và không được ánh xạ giả sang `PARAM_*`.

## Giả định kỹ thuật

- Tọa độ detection là polygon theo pixel trên ảnh gốc.
- Một block recognition có thể chứa nhiều từ. Bbox mức từ được nội suy theo vị trí ký tự trong block; đây là xấp xỉ được ghi rõ, không phải bbox từ do OCR engine cung cấp.
- Thứ tự từ ban đầu theo thứ tự block OCR. LayoutLMv3 dùng bbox chuẩn hóa nguyên trong đoạn `[0, 1000]`.
- Mỗi annotation gắn với đúng ảnh và snapshot OCR. Khi OCR thay đổi, annotation phải được kiểm tra lại thay vì tự động ghép bằng nội dung text.
