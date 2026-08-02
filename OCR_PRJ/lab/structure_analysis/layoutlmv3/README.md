# Thử nghiệm phân loại ngữ nghĩa bằng LayoutLMv3

Đây là thử nghiệm biệt lập để đo khả năng gán vai trò ngữ nghĩa cho OCR token/block trên phiếu chỉnh định relay. Mọi mã thử nghiệm nằm trong `lab/structure_analysis/`; mọi kết quả chạy nằm trong `output/layoutlmv3_token_classification/`.

## Trạng thái dữ liệu hiện tại

Kiểm kê ngày 2026-07-20 không tìm thấy ảnh trang 3 trở đi hoặc annotation BIO dùng được. Vì vậy chưa có cơ sở fine-tune hay báo cáo precision, recall và F1. Xem `DATA_AUDIT.md` và file output `dataset_audit.json`.

## Đường ống

1. Dùng hạ tầng detection và VietOCR hiện có qua `OCRProvider`; recognition vẫn cắt vùng từ ảnh gốc.
2. Tách text block thành word. Do OCR hiện chỉ có bbox block, bbox word được nội suy theo vị trí ký tự và được chuẩn hóa về `[0, 1000]`.
3. `LayoutLMv3Processor` nhận ảnh trang, danh sách word và bbox ngoài (`apply_ocr=False`). Trang dài được chia cửa sổ 512 token với phần chồng lấn.
4. Lưu ánh xạ đầy đủ `block_id → word_id → model token → nhãn → bbox` trong `predictions.json`.
5. Gộp chuỗi BIO thành entity trong `entities.json` và vẽ nhãn block lên ảnh gốc.
6. Chỉ tính chỉ số khi có ground truth hợp lệ và checkpoint có đúng schema mục tiêu.

Subtoken đầu tiên của một word nhận nhãn huấn luyện; subtoken còn lại dùng `-100`. Khi một word xuất hiện ở nhiều cửa sổ chồng lấn, xác suất được lấy trung bình trước khi chọn nhãn.

## Hai chế độ mô hình

### Suy luận pretrained

Checkpoint mặc định là `nnul/layoutlmv3-finetuned-funsd`, một checkpoint cộng đồng fine-tune từ `microsoft/layoutlmv3-base`. Hệ nhãn FUNSD không khớp `SECTION`, `RECORD_KEY`, `PARAM_CODE`, `PARAM_NAME`, `PARAM_VALUE`, `NOTE`. Chương trình giữ nguyên `model_label` và để `target_schema_label=null`; không có ánh xạ đoán mò.

Checkpoint `microsoft/layoutlmv3-base` chỉ là mô hình nền pretrain, không phải classifier đã học schema của dự án. Không dùng classifier khởi tạo ngẫu nhiên để tạo kết quả được gọi là suy luận.

### Sẵn sàng fine-tune

`annotation_schema.json`, `ANNOTATION_GUIDE.md`, validator, trình mã hóa, cấu hình train, Trainer và pipeline đánh giá đã được cung cấp. Script train chủ động dừng nếu không có annotation thật `split=train`.

## Cách chạy

Từ thư mục gốc dự án:

```powershell
python -m lab.structure_analysis.layoutlmv3.run_layoutlmv3 --mode audit
python -m lab.structure_analysis.layoutlmv3.run_layoutlmv3 --mode prepare
```

Sau khi đã thêm ảnh trang 3+ và hoàn tất annotation:

```powershell
python -m pip install -r lab/structure_analysis/layoutlmv3/requirements-layoutlmv3.txt
python -m lab.structure_analysis.layoutlmv3.train_layoutlmv3
python -m lab.structure_analysis.layoutlmv3.run_layoutlmv3 --mode evaluate --checkpoint lab/structure_analysis/output/layoutlmv3_token_classification/training/final_model
```

Suy luận pretrained trên trang 3+:

```powershell
python -m lab.structure_analysis.layoutlmv3.run_layoutlmv3 --mode inference
```

Có cờ `--allow-page1-smoke-test` để kiểm tra kỹ thuật duy nhất một trang 1 khi chưa có trang 3+. Kết quả này được đánh dấu rõ là smoke test và không được xem là kết quả đánh giá.

## Output

- `predictions.json`: dự đoán word/block, nhãn checkpoint, nhãn schema mục tiêu nếu tương thích và ánh xạ token.
- `entities.json`: thực thể BIO được ghép.
- `metrics.json`: token/entity precision, recall, F1, F1 từng lớp, thời gian suy luận và VRAM nếu có CUDA; khi thiếu ground truth, các chỉ số là `null`.
- `visualization/`: ảnh phủ bbox và nhãn.
- `dataset_audit.json`: bằng chứng về dữ liệu và annotation được tìm thấy.
- `annotation_queue/`, `training/`: mẫu gán nhãn và checkpoint, đều ở đúng output root.
- `readable_records.json`: bản ghi ứng viên dễ đọc theo dạng `code → name → values`; mỗi trang cũng có một file riêng trong `readable_pages/`. Tạo lại từ output dự đoán hiện có bằng `python -m lab.structure_analysis.layoutlmv3.build_readable_json`.
- `readable_records.csv`: một dòng cho mỗi bản ghi để kiểm tra bằng Excel; `readable_csv_pages/` chứa CSV từng trang, còn `unassigned_rows.csv` liệt kê các dòng OCR chưa đủ bằng chứng để gom. Tạo bằng `python -m lab.structure_analysis.layoutlmv3.build_readable_csv`. File dùng UTF-8 BOM để Excel hiển thị tiếng Việt.

`readable_records.json` là bước gom hình học sau OCR: block cùng dòng được chia thành mã, tên và giá trị từ các cột được suy ra theo các vị trí lặp lại; dòng kế tiếp chỉ được thêm vào giá trị trước khi có khoảng cách ngắn và căn theo cột giá trị. Nhãn FUNSD được lưu làm bằng chứng nhưng không quyết định vai trò relay. `grouping_confidence` đo độ mạnh của bằng chứng hình học, không phải độ chính xác đã được chứng minh.

## Giới hạn và ca thất bại

- Token classification chỉ cho biết loại thực thể. Nó không biết một `PARAM_VALUE` thuộc `PARAM_NAME` nào, đặc biệt trong quan hệ một-nhiều hoặc bảng không viền. Cần một bước relationship/record linking riêng sau thử nghiệm này.
- `PARAM_NAME` và `PARAM_VALUE` có thể đều được phân loại đúng nhưng vẫn ghép sai record nếu chỉ dựa trên thứ tự đọc.
- Bbox word nội suy kém chính xác khi block chứa khoảng trắng bất thường, text xoay, nhiều cột hoặc OCR gộp nhầm dòng.
- OCR mất từ làm mô hình không thể gán nhãn cho nội dung không tồn tại trong đầu vào.
- Watermark, bảng dày, chữ nhỏ và thứ tự block sai vẫn ảnh hưởng cả ảnh, text và bố cục.
- Chia cửa sổ có thể cắt entity dài; stride giảm nhưng không loại bỏ hoàn toàn vấn đề này.
- Checkpoint FUNSD chỉ phù hợp để kiểm tra đường ống, không chứng minh hiệu năng trên phiếu relay.
- Không tuyên bố kết quả đúng khi chưa có ground truth.
