# Sử dụng image Python 3.13 slim để tối ưu dung lượng
FROM python:3.13-slim

# Ngăn chặn Python ghi bytecode (.pyc) ra ổ đĩa
ENV PYTHONDONTWRITEBYTECODE=1
# Bắt buộc Python hiển thị output trực tiếp vào console
ENV PYTHONUNBUFFERED=1

# Cài đặt các thư viện hệ thống cần thiết (nếu có)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Đặt thư mục làm việc trong container
WORKDIR /app

# Sao chép requirements.txt và cài đặt thư viện
COPY requirements.txt /app/
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Sao chép toàn bộ mã nguồn dự án vào container
COPY . /app/

# Khởi chạy ứng dụng thông qua Daphne (ASGI) để hỗ trợ WebSockets cho Channels
# Chạy ở cổng 9000 như yêu cầu
CMD ["daphne", "-b", "0.0.0.0", "-p", "9000", "rms_project.asgi:application"]
