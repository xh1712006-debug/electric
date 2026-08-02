# Hướng dẫn xây dựng mô hình phân tích bố cục cho phiếu chỉnh định rơ-le

## Mục đích và phạm vi

Tài liệu này là điểm bàn giao cho Agent/kỹ sư tiếp theo xây dựng **Layout Analysis** cho các trang thông số của phiếu chỉnh định rơ-le, đặc biệt là trang 3 trở đi. Mục tiêu là biến ảnh gốc và OCR thành dữ liệu có cấu trúc, ví dụ một bản ghi `mã tham số - tên - giá trị`, có quan hệ với nhóm/đề mục chứa nó.

Tập ảnh hiện tại là một tập khảo sát bố cục tốt, nhưng **chưa đủ để chứng minh mô hình tổng quát đã học được**: phần lớn mỗi biến thể mới chỉ có một hoặc vài trang. Phải bổ sung nhiều trang và nhiều lần quét/phiên bản cho từng họ bố cục trước khi huấn luyện và đánh giá chính thức.

Nguồn ảnh khảo sát: `data/image/page3/`.

## Những họ bố cục đã quan sát

| Họ bố cục | Mẫu đại diện | Đặc trưng cần học |
| --- | --- | --- |
| Ba cột không kẻ viền | `7SJ622_1`, `7SJ622_2` | Mã, tên và giá trị thẳng cột bằng khoảng trắng; tiêu đề nhóm in đậm; giá trị có thể xuống dòng. |
| Bảng ba cột có dải giá trị | `C264_1`, `C264_2` | `Parameter`, `Range of value`, `Value`; tiêu đề nhóm trải toàn hàng; ô có nội dung xuống dòng; cuối trang có ghi chú tự do. |
| Bảng bốn cột thuộc tính | `GRL200_1` | Khóa, giá trị, đơn vị, mô tả; nhóm có dạng đường dẫn; mã có thể là chuỗi kỹ thuật như `AI1_Ch1_Ratio`. |
| Hai cột phân cấp không viền | `L90_1` | Tiêu đề đường dẫn viết hoa, nhóm con và cặp tên/giá trị căn theo cột nhưng không có lưới. |
| Bảng ba cột phân cấp | `P132_1` | Dòng nhóm và dòng tham số xen kẽ; mã kiểu thập phân; một số hàng chỉ biểu diễn cấp phân nhóm. |
| Bảng mã - tên - giá trị | `P443_1`, `P443_2`, `P543_1`, `P543_2` | Mã có phần thập lục phân như `09.0A`, `0A.01`; dòng tiêu đề mục trải hàng; lưới rõ. |
| Bảng chỉ số - hạng mục - mô tả - thiết lập | `PCS-902_1` đến `PCS-902_4` | Bốn cột, nhóm trải hàng, có hàng tiếp tục thiếu chỉ số, mô tả dài. |
| Nhiều bảng bốn cột trên một trang | `PCS9611_1` đến `PCS9611_4` | Bảng `No - Menu text - Explanation - Setting`; bảng/nhóm lồng nhau; ô mô tả và giá trị có thể nhiều dòng. |

Các ảnh cùng họ là biến thể khác dữ liệu hoặc chất lượng quét, không được coi là mẫu kiểm thử độc lập nếu cùng nguồn tài liệu.

## Đặc trưng chung và nhiễu cần loại trừ

- Header chung, tiêu đề phiếu, số phiếu, số trang, watermark chéo và dấu đỏ là nội dung tài liệu nhưng thường **không phải tham số chỉnh định**.
- Văn bản có cả tiếng Việt và tiếng Anh; OCR có thể sai dấu, gộp/tách từ hoặc gộp nhầm ô.
- Một giá trị/tên/mô tả có thể bao gồm nhiều dòng vật lý. Một dòng vật lý không đồng nghĩa một bản ghi nghiệp vụ.
- Bảng có thể có đường kẻ, không có đường kẻ, có hàng tiêu đề trải nhiều cột, hoặc nhiều bảng trên cùng trang.
- Mã tham số không có duy nhất một định dạng. Regex chỉ nên là tín hiệu bổ sung, không phải điều kiện quyết định.

## Kết quả dữ liệu cần hướng đến

Giữ nguyên OCR gốc và tách rõ kết quả mô hình với kết quả đã được con người xác nhận.

```json
{
  "document_id": "P443_1",
  "page_number": 3,
  "groups": [
    {"group_id": "g-01", "title": "CONFIGURATION", "parent_group_id": null}
  ],
  "records": [
    {
      "record_id": "r-019",
      "group_id": "g-01",
      "key": {"text": "09.03", "source_block_ids": ["b-21"]},
      "name": {"text": "Active Settings", "source_block_ids": ["b-22"]},
      "values": [{"text": "Group 1", "source_block_ids": ["b-23"]}],
      "confidence": 0.91,
      "status": "model_candidate"
    }
  ]
}
```

Không tự ghi đè `raw_ocr`, không xóa tọa độ gốc, và không coi `confidence` là bằng chứng đúng.

## Schema gán nhãn

### Nhãn thực thể chung

Gán nhãn theo từ (BIO) để fine-tune LayoutLMv3, với schema chung sau:

- `SECTION`: tiêu đề nhóm/phân nhóm.
- `RECORD_KEY`: chỉ số, khóa hoặc định danh bản ghi không phải mã tham số.
- `PARAM_CODE`: mã kỹ thuật của tham số.
- `PARAM_NAME`: tên tham số/hạng mục/menu.
- `PARAM_VALUE`: giá trị thiết lập; bao gồm cả giá trị bị xuống dòng.
- `RANGE`: dải hay điều kiện giá trị.
- `UNIT`: đơn vị nếu nó là một ô/thực thể riêng.
- `DESCRIPTION`: lời giải thích kỹ thuật của tham số.
- `NOTE`: lưu ý/đoạn tự do.
- `HEADER_FOOTER`: thông tin trang, số phiếu, tiêu đề chung không đưa vào cấu hình.
- `O`: phần còn lại, watermark, dấu hoặc nhiễu.

Các nhãn trên mô tả **vai trò**, không mô tả tên mẫu phiếu hay vị trí cố định. Có thể dùng `B-` và `I-` cho mọi thực thể nhiều từ.

### Nhãn quan hệ cần gán riêng

Token classification không biết chắc giá trị nào thuộc tham số nào. Sau khi gán nhãn thực thể, cần thêm quan hệ ở cấp block/thực thể:

- `BELONGS_TO_GROUP`: bản ghi hoặc nhóm con thuộc nhóm cha.
- `HAS_VALUE`: tên/mã tham số nối tới một hay nhiều giá trị.
- `HAS_RANGE`, `HAS_UNIT`, `HAS_DESCRIPTION`: nối tới các cột phụ.
- `CONTINUES`: đoạn tiếp theo nối vào thực thể bị xuống dòng.
- `SAME_RECORD`: các thực thể ở cùng một bản ghi.

Quan hệ phải được lưu bằng ID nguồn, không suy ra lại chỉ từ chuỗi OCR.

## Dữ liệu đầu vào chuẩn

Pipeline OCR đã có sẵn ở `src/detection/` và `src/recognition/`. Tái sử dụng PP-OCR detector với tiền xử lý watermark đã kiểm chứng và VietOCR recognition; không tạo một OCR thứ hai trong lab.

Mỗi word/block tối thiểu cần có:

```json
{
  "block_id": "b-23",
  "text": "Group 1",
  "bbox_px": [x0, y0, x1, y1],
  "bbox_1000": [0, 0, 1000, 1000],
  "confidence": 0.97,
  "page_number": 3
}
```

`bbox_1000` là bounding box chuẩn hóa theo chiều rộng/cao ảnh, bắt buộc cho LayoutLMv3. Cần duy trì ánh xạ đầy đủ:

`ảnh gốc → block OCR → word OCR → token mô hình → thực thể dự đoán → bản ghi/nhóm`.

Không dùng ảnh threshold mờ để recognition. Dùng ảnh gốc để nhận dạng và chỉ sử dụng tọa độ detection làm vùng cắt, như pipeline hiện tại.

## Kiến trúc khuyến nghị: lai, phân loại theo họ bố cục

Không nên chọn một trong hai cực đoan: một mô hình hoàn toàn mù bố cục, hoặc một parser cứng cho từng mẫu phiếu. Với khoảng 20 mẫu phiếu cố định nhưng khác nhau rõ rệt, kiến trúc phù hợp là:

```text
Ảnh gốc
  → Detection + Recognition dùng chung
  → Phân loại họ bố cục (tín hiệu hỗ trợ)
  → Nhận dạng vai trò chung bằng LayoutLMv3
  → Phát hiện bảng/hàng/cột + liên kết quan hệ
  → Liên kết nhóm xuyên trang
  → điểm tin cậy và Human Review
```

### 1. Phân loại họ bố cục

Classifier nên trả về họ bố cục như `bang_3_cot_ma_ten_gia_tri`, `bang_4_cot_co_mo_ta`, `hai_cot_khong_vien`, `nhieu_bang_phan_cap`, cùng xác suất. Có thể huấn luyện classifier ảnh nhẹ hoặc suy ra từ đặc trưng hình học/đường kẻ.

Classifier **không** được quyết định trực tiếp giá trị dữ liệu. Nó chỉ chọn prior/cấu hình mềm cho bước cấu trúc: số cột dự kiến, khả năng có lưới, loại hàng tiêu đề và cách xử lý dòng quấn. Nếu xác suất thấp, chạy chiến lược tổng quát và đưa trang vào review.

Chỉ thêm classifier theo đúng tên mẫu phiếu khi có đủ dữ liệu cho mẫu đó và có nhu cầu kiểm soát vận hành. Ngay cả khi nhận diện đúng tên mẫu, không dùng tọa độ pixel cố định cho trường nghiệp vụ.

### 2. Mô hình vai trò chung

Fine-tune LayoutLMv3 trên toàn bộ các họ, dùng ảnh trang + text OCR + `bbox_1000`, với các nhãn chung ở trên. Mô hình này học rằng một khối là `PARAM_NAME`, `PARAM_VALUE`, `SECTION`... chứ không học “ô thứ 3 của P443”.

Thí nghiệm hiện tại ở `lab/structure_analysis/layoutlmv3/` đã hỗ trợ mapping OCR/token, inference, chuẩn bị dữ liệu, annotation guide và huấn luyện. Checkpoint FUNSD dùng trong thử nghiệm chỉ để kiểm tra đường ống: nhãn FUNSD không khớp schema phiếu nên không được dùng làm kết quả nghiệp vụ.

### 3. Trích cấu trúc và liên kết bản ghi

Đây là bước riêng sau LayoutLMv3.

- Phát hiện đường bảng và các đường căn chỉnh để ước lượng cột/hàng theo tọa độ chuẩn hóa.
- Gom các block cùng hàng/cùng ô; dùng `CONTINUES` để nối đoạn quấn xuống dòng.
- Dựa trên vai trò dự đoán, quan hệ hình học, hàng/cột và họ bố cục để tạo `SAME_RECORD`, `HAS_VALUE`, `BELONGS_TO_GROUP`.
- Với bảng có lưới, ưu tiên quan hệ cùng hàng/cùng cột. Với bố cục không viền, ưu tiên cụm căn trái/căn phải và khoảng cách dọc.
- Không gán một value cho parameter chỉ vì chúng đứng gần nhau; nếu nhiều ứng viên có điểm gần nhau, trả về độ không chắc chắn và yêu cầu review.

### 4. Nhóm xuyên trang

LayoutLMv3 nhìn một trang một lần. Hệ thống cần bộ liên kết ở cấp tài liệu giữ `document_id`, thứ tự trang, stack `group_path` và tín hiệu “tiêu đề tiếp tục”. Nếu đầu trang mới không có tiêu đề, kế thừa nhóm đang mở ở trang trước với cờ `inherited_from_previous_page`; không coi đó là nhãn do model dự đoán.

## Quy trình gán nhãn và chia dữ liệu

1. Chạy OCR ổn định, đóng băng `raw_ocr.json` cho từng trang; người gán nhãn sửa text/bbox sai phải ghi phiên bản thay đổi.
2. Gán nhãn thực thể BIO trên word/block, sau đó gán group và quan hệ. Bắt đầu với những hàng rõ nhất, nhưng phải bao gồm dòng quấn, dòng nhóm và note.
3. Mỗi họ bố cục phải có nhiều tài liệu và biến thể quét trong train/validation/test; đừng chỉ lặp bản sao dữ liệu của một trang.
4. Chia theo **tài liệu/phiếu**, không chia ngẫu nhiên theo dòng. Không để trang gần giống của cùng phiếu xuất hiện ở cả train và test.
5. Vì phạm vi vận hành hiện chỉ khoảng 20 mẫu phiếu, tạo hai đánh giá: (a) dữ liệu cùng các họ đã biết nhưng là tài liệu khác; (b) một họ/mẫu được giữ lại hoàn toàn để đo mức tổng quát hóa thực sự.
6. Không tạo nhãn giả hoặc báo F1 khi chưa có ground truth đã hoàn thành.

## Các chỉ số phải báo cáo

Báo cáo riêng cho từng họ bố cục và toàn tập:

- F1 token và F1 thực thể theo lớp.
- F1 quan hệ (`HAS_VALUE`, `SAME_RECORD`, `BELONGS_TO_GROUP`).
- Tỷ lệ khôi phục bản ghi đúng hoàn toàn: khóa/mã, tên, toàn bộ giá trị và nhóm đúng.
- Độ chính xác nối nội dung xuống dòng.
- Tỷ lệ trang/bản ghi bị đưa vào human review, thời gian xử lý, và lỗi OCR làm hỏng layout.

Một `PARAM_NAME` đúng và một `PARAM_VALUE` đúng nhưng nối sai với nhau vẫn là lỗi trích xuất quan trọng; không được che khuất bằng F1 token cao.

## Lộ trình triển khai cho Agent tiếp theo

1. Kiểm tra lại OCR trên mọi trang, lưu version và xuất word-level bbox thật nếu engine hỗ trợ.
2. Dùng các họ trong bảng trên làm taxonomy ban đầu; bổ sung ảnh trang 3+ còn thiếu cho mỗi họ.
3. Hoàn thiện dữ liệu annotation theo `lab/structure_analysis/layoutlmv3/ANNOTATION_GUIDE.md`, thêm annotation quan hệ/group ở cấp thực thể.
4. Tạo split theo tài liệu, sau đó fine-tune LayoutLMv3 chỉ khi có nhãn đã kiểm tra.
5. Xây dựng linker quan hệ độc lập, có thể bắt đầu bằng hình học + đường bảng, rồi học một relation scorer khi đủ annotation.
6. Thêm classifier họ bố cục làm routing mềm và thử nghiệm ablation: tổng quát không routing, routing theo họ, routing theo tên mẫu.
7. Đặt ngưỡng review theo confidence của thực thể **và** của quan hệ, không chỉ confidence OCR.

## Những failure case cần giữ trong tập kiểm thử

- Watermark chéo che chữ hoặc đè lên đường bảng.
- Mô tả/giá trị dài bị xuống hai hoặc nhiều hàng.
- Hàng tiêu đề trải toàn bộ bảng và hàng tiếp tục có ô trống.
- Mã dạng số, số-thập phân, thập lục phân và chuỗi có gạch dưới.
- Hai bảng trên cùng một trang và tiêu đề lồng nhau.
- Cột không có đường viền, lệch nhẹ do scan.
- Header/footer giống dữ liệu tham số nhưng phải bị loại khỏi kết quả.
- Giá trị lặp lại như `Enabled`, `Disabled`, `Standard` ở nhiều hàng: không được nối nhầm.

## Quyết định kiến trúc

**Dùng một mô hình semantic tổng quát làm lõi, cộng classifier họ bố cục để điều hướng bước khôi phục cấu trúc.** Đây là lựa chọn tốt nhất cho bộ dữ liệu hiện tại:

- Mô hình chung tái sử dụng được vai trò giống nhau giữa 7SJ622, P443/P543, PCS-902, PCS9611... và giảm số parser phải bảo trì.
- Routing theo họ bố cục xử lý sự khác nhau thật sự giữa bảng có viền, bảng nhiều cột, hai cột không viền và bảng phân cấp.
- Parser riêng theo từng tên mẫu chỉ là phương án dự phòng có kiểm soát cho mẫu quan trọng, sau khi mô hình tổng quát/routing vẫn không đạt; nó không phải kiến trúc mặc định.

