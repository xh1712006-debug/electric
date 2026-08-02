# Text detection comparison lab (Phòng thí nghiệm so sánh tính năng phát hiện văn bản)

Phòng thí nghiệm (lab) này chạy mọi hình ảnh nguồn trong `data/image` qua một bộ phát hiện văn bản (text detector) và ghi một bản sao có chú thích cộng với kết quả phát hiện dưới dạng JSON vào:

```text
output/image_from_detection/{model_name}/
```

Các hình ảnh gốc không bao giờ bị thay đổi. Mỗi thư mục đầu ra (output directory) phản chiếu cấu trúc thư mục con của thư mục đầu vào. Một file `run_summary.json` ở cấp gốc ghi lại thời gian thực thi, số lượng vùng phát hiện được và lỗi.

## Các mô hình (Models)

| Model id | Kiến trúc (Architecture) | Backend | Cài đặt mô hình (Model setup) |
| --- | --- | --- | --- |
| `dbnetpp_resnet50` | DBNet++ / ResNet-50 | PaddleOCR | Cần thư mục chứa mô hình suy luận Paddle đã export |
| `dbnet_mobilenetv3` | DBNet / MobileNetV3 | PaddleOCR | Cần thư mục chứa mô hình suy luận Paddle đã export |
| `craft` | CRAFT | EasyOCR | Trọng số (weights) tự động tải xuống ở lần chạy đầu tiên |
| `psenet` | PSENet | PaddleOCR | Cần thư mục chứa mô hình suy luận Paddle đã export |
| `pp_ocr_detector` | PP-OCRv5 Mobile detector | PaddleOCR 3.x | Bộ phát hiện mặc định tự động tải xuống ở lần chạy đầu |

PaddleOCR hỗ trợ DB với MobileNetV3, PSE và DB++/ResNet-50 trong bộ sưu tập mô hình phát hiện của nó. Lab cố tình yêu cầu các thư mục suy luận export tường minh đối với ba mô hình Paddle không phải mặc định, để một thử nghiệm không thể âm thầm chạy một bộ phát hiện khác đi.

## Cài đặt (Setup)

Tạo và kích hoạt môi trường ảo, sau đó cài đặt các thư viện phụ thuộc:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r lab/detection/requirements.txt
```

Đối với CUDA, hãy cài đặt bản build PaddlePaddle tương ứng với runtime CUDA đã cài trước khi cài đặt `paddleocr`.

Export/tải xuống chính xác các mô hình suy luận Paddle và đặt mỗi thư mục vào đây (hoặc chỉnh sửa `models.json`):

```text
lab/detection/models/dbnetpp_resnet50/
lab/detection/models/dbnet_mobilenetv3/
lab/detection/models/psenet/
```

Mỗi thư mục phải là một thư mục mô hình suy luận Paddle chứa mô hình suy luận và các file tham số. Không trỏ nhiều mục (entries) vào cùng một mô hình PP-OCR: điều đó làm vô hiệu hóa sự so sánh.

Các thư mục hiện có dưới `lab/detection/downloads/` là các checkpoint huấn luyện (`best_accuracy.pdparams`), không phải mô hình suy luận. Chúng được ghi lại trong `models.json` để truy xuất nguồn gốc nhưng phải được export với cấu hình PaddleOCR khớp với chúng trước khi ba thử nghiệm có thể chạy. Hãy để các mục `model_dir` của chúng trỏ đến `lab/detection/models/...`; và đặt các file đã export vào đó.

### Export checkpoint DBNet++ đã tải xuống

Script `export_dbnetpp.ps1` export file `det_r50_db++_icdar15_train/best_accuracy.pdparams` với cấu hình khớp `det_r50_db++_icdar15.yml`. Đầu tiên, lấy source checkout PaddleOCR 2.x bao gồm cấu hình này và kích hoạt môi trường Python tương thích với checkout đó. Sau đó chạy:

```powershell
.\lab\detection\export_dbnetpp.ps1 -PaddleOcrRoot C:\path\to\PaddleOCR -Python C:\path\to\legacy-python.exe
```

Nó ghi mô hình suy luận vào `lab/detection/models/dbnetpp_resnet50/`, nơi đã được cấu hình trong `models.json`. Script này từ chối ghi đè lên một bản export đã có sẵn.

## Chạy (Run)

Smoke-test CRAFT và PP-OCR trên năm hình ảnh:

```powershell
python lab/detection/run_comparison.py --models craft pp_ocr_detector --limit 5
```

Chạy tất cả các mô hình đã cấu hình trên tất cả hình ảnh:

```powershell
python lab/detection/run_comparison.py
```

## So sánh xử lý tiền kỳ giảm watermark (watermark-reduction preprocessing)

Lệnh sau đây chạy PP-OCR trên hình ảnh gốc, hình ảnh độ tương phản cục bộ (`clahe`) và hình ảnh triệt tiêu watermark hai giai đoạn Otsu được chọn tự động (`adaptive_threshold`). Nó ghi vào một cây thư mục mới và không bao giờ ghi đè lên `output/image_from_detection/`:

```powershell
python lab/detection/run_comparison.py --models pp_ocr_detector --preprocess original clahe adaptive_threshold --overwrite
```

Kết quả được tổ chức như sau:

```text
output/image_detection_preprocessing_comparison/
  pp_ocr_detector/
    adaptive_threshold/
      preprocessed/  # hình ảnh thực sự được gửi tới bộ phát hiện
      annotated/     # cùng hình ảnh với các vùng phát hiện được vẽ lên
      detections/    # polygons, điểm số và thời gian chạy dưới dạng JSON
```

Chỉ sử dụng `--device cuda` sau khi đã cài đặt một bản build PaddlePaddle tương thích CUDA. Các kết quả hiện có được bảo lưu; thêm `--overwrite` để tạo lại chúng.

Trên Windows CPU, lab vô hiệu hóa tính năng tăng tốc mộtDNN/MKLDNN tùy chọn của Paddle. Điều này tránh được lỗi `fused_conv2d` thường thấy ở các mô hình PaddleOCR 2.x cũ và chỉ ảnh hưởng tới tốc độ, không ảnh hưởng tới bộ phát hiện nào đang được đánh giá.

Lệnh này chỉ trả về mã thoát (exit code) khác 0 khi một mô hình đã cấu hình bị lỗi. Một mục DBNet++/DBNet MobileNetV3/PSENet mà không có checkpoint riêng của nó được báo cáo là `not-configured`, do đó các thử nghiệm CRAFT và PP-OCR sẵn có vẫn có thể kết thúc. Đọc `output/image_from_detection/run_summary.json` để biết trạng thái của từng mô hình.
