# Lab tái tạo bố cục phiên bản 2

Lab này kế thừa `lab/structure_analysis/` và dùng `predictions.json` OCR đã cache làm đầu vào chính. Detector PP-OCR và VietOCR chỉ chạy lại trên những ô mà block OCR cũ thực sự vượt qua biên ô.

Mục tiêu là xử lý các họ bố cục trong `LAYOUT_ANALYSIS_MODEL_GUIDE.md` mà bộ gom cũ không xử lý tốt: mã có ký tự hexa, bảng ba/bốn cột, bảng có mô tả/dải giá trị/đơn vị và dòng quấn.

## Phương pháp

1. Tách các thành phần lưới liên thông để phát hiện từng vùng bảng độc lập. Mỗi vùng có biên cột và biên hàng riêng; PCS9611 vì thế có thể chứa hai bảng với độ rộng cột khác nhau trên cùng trang.
2. Với bảng có lưới, mỗi dải giữa hai đường ngang là một logical row. Bounding box cao hoặc chồng lấn không còn được phép gộp hai hàng.
3. Nếu block OCR cắt đáng kể qua biên ô và hàng có bằng chứng đa cột, detector chạy lại trong từng ô trên ảnh đã giảm watermark; VietOCR nhận dạng crop từ ảnh gốc. Tiêu đề nhóm đơn lẻ trải toàn hàng không bị cắt.
4. Nếu không có lưới (như 7SJ622), tìm các cột lặp lại rồi gom dòng bằng đồng thuận baseline đa cột. Một block cao trong một cột không được kéo hai dòng của các cột khác vào nhau.
5. Dùng header chung như `Value`, `Range`, `Unit`, `Description`, `Setting` để đặt vai trò cột; nếu không có header thì dùng thứ tự cột như một prior yếu.
6. Trong bảng, nội dung nhiều dòng trong cùng cell-row luôn thuộc cùng record. Ngoài bảng, một dòng chỉ nối vào record trước khi không có mã/chỉ số mới, không tự tạo đủ các cột của record mới, nằm gần và thụt vào cột dữ liệu.

Lab không dùng tọa độ cố định, không có luật riêng theo tên phiếu, và không khẳng định dữ liệu đã đúng.

## Chạy

```powershell
.\lab\structure_analysis_2\.venv\Scripts\python.exe -m pip install -r lab\structure_analysis_2\requirements.txt
.\lab\structure_analysis_2\.venv\Scripts\python.exe -m lab.structure_analysis_2.run_experiment
```

Dùng `--cell-ocr off` nếu chỉ muốn kiểm tra thuật toán lưới/fallback mà không nạp model OCR. Mặc định là `--cell-ocr auto`; có thể thêm `--gpu` khi máy đã có PaddlePaddle/PyTorch tương thích GPU.

Mặc định nguồn là `lab/structure_analysis/output/layoutlmv3_token_classification/predictions.json`.

Kết quả nằm trong `lab/structure_analysis_2/output/`:

- `reconstructed_layouts.json`: toàn bộ kết quả và metadata cột.
- `pages/*.json`: kết quả theo trang để review.
- `records.csv`: bản ghi ứng viên ở dạng dễ mở bằng Excel.
- `records_by_document/*.csv`: mỗi phiếu một file CSV; nếu một phiếu có nhiều trang thì các trang được ghép vào cùng file và giữ thứ tự `page_number`.
- `table_grids/*.png`: ảnh gốc phủ đường lưới được phát hiện, để kiểm tra bước tách cột.
- `cell_ocr_overrides.json`: nội dung, confidence, cell bbox và block gây kích hoạt cho các ô đã OCR lại.

Nếu `records.csv` đang được mở bằng Excel, Windows không cho ghi đè. Lab sẽ tự ghi file mới có timestamp thay vì dừng giữa chừng.

## Giới hạn

- Chưa có gán nhãn thật nên đây là baseline hình học, không phải mô hình đã học.
- OCR lại theo ô sửa được trường hợp block gộp qua biên, nhưng không thể đảm bảo phục hồi ký tự mà detector vẫn bỏ sót hoàn toàn.
- Phát hiện đường kẻ trực tiếp từ ảnh và mô hình liên kết quan hệ học máy là bước tiếp theo khi có ground truth.
- Với PCS-902 và PCS9611, OCR hiện tại gộp `Index`/`No` với `Item`/`Menu text` ở một số hàng. Để tách chính xác cần bước nhận diện lưới bảng từ ảnh gốc, yêu cầu môi trường Python có OpenCV hoặc Pillow.
