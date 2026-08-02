# Nhận diện và trích xuất Page 1

## Bối cảnh phiếu

- Một PDF là một phiếu nhiều trang.
- Page 1 dùng chung mẫu giữa các phiếu, nhưng chiều cao ô có thể thay đổi theo độ dài dữ liệu.
- Page 2 có mẫu chung nhưng không có dữ liệu nghiệp vụ quan trọng: chỉ xác nhận header và đánh dấu `ignored`.
- Page 3+ chứa thông tin chỉnh định rơ-le; xử lý bằng layout analysis hiện có.
- Mọi trang có header chung; nửa phải chứa `Số phiếu` và `Trang: x/y`.
- Cuối phiếu có phần `Lưu ý` quan trọng, không phải bảng và cần extractor riêng ở giai đoạn document-level.

## Mục tiêu page 1

Trích xuất các field nghiệp vụ của trang đầu thành dữ liệu có nguồn gốc (`source_page`, cell/block OCR, confidence), không ép page 1 vào schema bảng `parameter_name/value` của page 3+.

## Phương pháp được chọn

Dùng **template-aware geometric extraction**:

1. Xác nhận page 1 bằng `Trang: 1/x`, anchor text đặc trưng và vị trí trong PDF; không chỉ dựa vào index.
2. Phát hiện Table 01, kể cả khi ảnh scan bị nghiêng hoặc một số đường phân cách nhỏ bị mất.
3. Chuẩn hóa Table 01 về topology cố định gồm 7 hàng và hai nửa trái/phải. Canonical field được sở hữu bởi `row + side + sub-slot`, không phụ thuộc từ ngữ OCR của label.
4. Tách label/value bên trong mỗi slot bằng hình học, dấu `:` và biên cột. Nhãn gốc đọc từ phiếu được lưu riêng trong `source_labels`.
5. Nối toàn bộ text nhiều dòng nằm trong cùng slot. Nếu slot chỉ có label thì field value là `null`; các hàng sau không bị dịch chuyển lên.
6. Từ điển label/alias chỉ dùng để hỗ trợ tách label khỏi value và làm fallback khi thật sự không dựng được lưới, không quyết định canonical field trong đường chạy chính.
7. Table 02 (`Nguyên tắc hoạt động...`) hiện vẫn được đánh dấu `protection_principle_table` và bỏ qua.
8. Xác thực định dạng/các field bắt buộc; không tự đoán khi thiếu dữ liệu, thay vào đó ghi warning.

Không dùng LayoutLMv3 ở giai đoạn đầu. Chỉ cân nhắc khi page 1 có nhiều biến thể đến mức anchor, grid và quan hệ label--value không còn ổn định.

## Schema field

Tạo manifest riêng, ví dụ `src/layout_analysis/schemas/relay_form_fields.yaml`. Tên logic ổn định bằng tiếng Anh; label/alias phản ánh đúng biểu mẫu và lỗi OCR thường gặp.

```yaml
page_roles:
  cover:
    fields:
      ticket_number:
        labels: ["Số phiếu", "Số phiếu chỉnh định"]
        type: string
        required: true
        validation: ticket_number
        source_policy: header_right
      relay_type:
        labels: ["Loại rơ-le", "Type", "Relay type"]
        type: string
        required: true
        source_policy: right_or_below_cell
      adjustment_reason:
        labels: ["Nội dung chỉnh định", "Lý do chỉnh định"]
        type: multiline_text
        allow_multiline: true
        source_policy: right_or_below_cell
```

Mỗi field nên có: `labels`, `aliases`, `type`, `required`, `validation`, `allow_multiline` và `source_policy`.

Tách tối thiểu ba nhóm:

- `common_header_fields`: `ticket_number`, `page_number`, `total_pages`.
- `cover_fields`: field nghiệp vụ riêng của page 1.
- `relay_setting_fields`: `parameter_name`, `value`, `range`, `unit`, `description` của page 3+.

## Output page 1

```json
{
  "page_number": 1,
  "page_role": "cover",
  "layout_strategy": {"cover_fields": "table_structure"},
  "fields": {
    "circuit_breaker": {
      "text": "273",
      "matched_label": "Máy cắt",
      "source_page": 1,
      "source_cell": "table_01:1:left",
      "source_block_ids": ["ocr_12"],
      "confidence": 0.94
    }
  },
  "source_labels": {
    "circuit_breaker": {
      "text": "Ngăn máy cắt",
      "canonical_field": "circuit_breaker"
    },
    "relay_version": {
      "text": "Phiên bản rơ-le",
      "canonical_field": "relay_version"
    }
  },
  "unassigned_blocks": [],
  "warnings": []
}
```

## Lộ trình triển khai

1. Audit nhiều page 1 đại diện và thống nhất danh sách field/alias với người nghiệp vụ.
2. Tạo lab riêng để đánh giá grid, cell assignment và label--value association trên page 1.
3. Viết test cho ô merge, text nhiều dòng, row cao và lỗi OCR nhẹ.
4. Chạy toàn bộ page 1, lưu overlay/cell evidence để review.
5. Production implementation nằm tại `src/layout_analysis/page1/`.
6. Sau đó mới xây document-level assembler để kết hợp page 1, page 2 bị bỏ qua, page 3+ và phần `Lưu ý`.

## Giới hạn hiện tại

Table 02 của page 1 chưa được trích xuất. Phần `Lưu ý` cuối phiếu và document-level assembler nối page 1/page 3+ vẫn là các hạng mục riêng.
