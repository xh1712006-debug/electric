# Hướng dẫn gán nhãn

## Nguyên tắc

Chỉ gán nhãn trên trang 3 trở đi. Nhãn mô tả vai trò ngữ nghĩa, không mô tả tên mẫu relay, tọa độ cố định hoặc số thứ tự dòng. Người gán nhãn phải nhìn cả ảnh trang, nội dung OCR và ngữ cảnh xung quanh.

Mỗi từ có đúng một nhãn BIO:

- `O`: nội dung không thuộc các vai trò mục tiêu.
- `B-SECTION`, `I-SECTION`: tiêu đề một vùng/nhóm logic.
- `B-RECORD_KEY`, `I-RECORD_KEY`: khóa nhận diện một bản ghi, ví dụ tên entry hoặc tên đối tượng đứng đầu bản ghi.
- `B-PARAM_CODE`, `I-PARAM_CODE`: mã tham số tổng quát như `003.085`.
- `B-PARAM_NAME`, `I-PARAM_NAME`: tên hoặc mô tả tham số.
- `B-PARAM_VALUE`, `I-PARAM_VALUE`: giá trị tham số; có thể dài nhiều dòng.
- `B-NOTE`, `I-NOTE`: ghi chú không phải giá trị chính.

`B-` đánh dấu từ đầu tiên của một thực thể; các từ tiếp theo của cùng thực thể dùng `I-`. Một thực thể có thể tiếp tục ở dòng vật lý tiếp theo. Không bắt đầu lại bằng `B-` chỉ vì text bị xuống dòng.

## Các trường hợp quan trọng

Với `003.085 | Fct. assig. trigger | 040.077 Starting IN>`:

- `003.085` là `B-PARAM_CODE`.
- `Fct.` là `B-PARAM_NAME`; các từ còn lại của tên là `I-PARAM_NAME`.
- `040.077` là `B-PARAM_VALUE`; các từ còn lại của cùng giá trị là `I-PARAM_VALUE`.
- Một giá trị tiếp theo là một thực thể `PARAM_VALUE` mới và bắt đầu bằng `B-PARAM_VALUE`.

Với giá trị bị xuống dòng như `Direct I/P 1-1 On ((khóa` rồi `bảo vệ so lệch tại chỗ))`, toàn bộ chuỗi là một thực thể `PARAM_VALUE`: từ `Direct` dùng `B-PARAM_VALUE`, mọi từ tiếp theo, kể cả dòng sau, dùng `I-PARAM_VALUE`.

Không suy luận quan hệ trong file nhãn token. Việc hai thực thể lần lượt được gán `PARAM_NAME` và `PARAM_VALUE` không tự động khẳng định chúng thuộc cùng bản ghi.

## Quy trình

1. Thêm ảnh trang 3+ vào nguồn dữ liệu, giữ số trang trong tên file hoặc metadata.
2. Chạy chế độ `prepare` để tạo JSON nháp trong `output/layoutlmv3_token_classification/annotation_queue/`.
3. Sao chép file nháp cần gán nhãn vào thư mục `layoutlmv3/annotations/`.
4. Điền nhãn cho mọi từ, chọn `split`, đổi `status` thành `completed`.
5. Chạy lại chế độ `audit`. Chỉ file vượt qua validator mới được dùng.

## Chia tập dữ liệu

Chia theo tài liệu/relay template, không chia ngẫu nhiên các trang của cùng một tài liệu sang nhiều tập. Tập kiểm thử nên chứa template chưa xuất hiện trong tập train nếu mục tiêu là đo khả năng tổng quát hóa. Không dùng cùng một ảnh hoặc biến thể gần như trùng lặp ở nhiều split.

## Kiểm tra chất lượng

- Hai người nên gán nhãn độc lập một phần dữ liệu và thống nhất các trường hợp mơ hồ.
- Ghi lý do vào `annotation_notes` khi một vùng có thể là `RECORD_KEY` hoặc `PARAM_NAME`.
- Nếu OCR sai chính tả, nhãn vẫn dựa trên vai trò của vùng; không sửa text trong annotation mà không tái tạo snapshot OCR.
- Nếu bbox word nội suy không đủ chính xác, nên nâng OCR pipeline để xuất bbox mức từ trước khi gán nhãn quy mô lớn.
