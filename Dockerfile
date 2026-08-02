# Sử dụng image Python 3.12 slim để tương thích với OCR_PRJ (yêu cầu Python <= 3.12)
FROM python:3.12-slim

# Ngăn chặn Python ghi bytecode (.pyc) ra ổ đĩa
ENV PYTHONDONTWRITEBYTECODE=1
# Bắt buộc Python hiển thị output trực tiếp vào console
ENV PYTHONUNBUFFERED=1

# Cài đặt các thư viện hệ thống cần thiết (đã bổ sung các thư viện cho OCR như poppler, opencv)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev poppler-utils libgl1 libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Đặt thư mục làm việc trong container
WORKDIR /app

# Sao chép requirements.txt gốc và cài đặt
COPY requirements.txt /app/
COPY vendor /app/vendor/
RUN pip install --upgrade pip \
    && pip install --find-links=/app/vendor -r requirements.txt

# Sao chép toàn bộ mã nguồn dự án vào container (bao gồm cả OCR_PRJ)
COPY . /app/

# Cài đặt thư viện của OCR_PRJ (cần mạng để tải)
RUN pip install -r OCR_PRJ/src/debug_ui/requirements-full.txt

# Khởi chạy ứng dụng thông qua Daphne (ASGI) để hỗ trợ WebSockets cho Channels
# Chạy ở cổng 9000 như yêu cầu
CMD ["daphne", "-b", "0.0.0.0", "-p", "9000", "rms_project.asgi:application"]
