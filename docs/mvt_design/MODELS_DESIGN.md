# Đặc tả Cơ sở Dữ liệu (Django + PostgreSQL)

**Database:** PostgreSQL 15+
**ORM:** Django ORM (PostgreSQL Backend)

Sử dụng mô hình CSDL quan hệ chuẩn (SQL) kết hợp với kiểu dữ liệu `JSONField` (JSONB) của PostgreSQL để xử lý các dữ liệu linh hoạt (như OCR) mà không cần phá vỡ cấu trúc của CSDL.

## 1. Khai báo Models
Sử dụng thư viện chuẩn `django.db.models`.

### 1.1 Quản lý Tổ chức & Phân quyền
Sử dụng Auth User mặc định của Django, mở rộng bằng Profile.

```python
from django.db import models
from django.contrib.auth.models import User

class Organization(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    org_type = models.CharField(max_length=50) # VTC, OPERATION, TRANSMISSION...
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
```

### 1.2 Trạm Biến áp & Rơ-le (Quan hệ 1-N)
Xây dựng quan hệ Trạm -> Ngăn lộ -> Rơ-le -> Cài đặt.

```python
class Station(models.Model):
    station_code = models.CharField(max_length=50, unique=True)
    station_name = models.CharField(max_length=200)
    location = models.CharField(max_length=255)

class Bay(models.Model):
    station = models.ForeignKey(Station, related_name='bays', on_delete=models.CASCADE)
    bay_code = models.CharField(max_length=50)
    bay_name = models.CharField(max_length=100)

class Relay(models.Model):
    bay = models.ForeignKey(Bay, related_name='relays', on_delete=models.CASCADE)
    relay_code = models.CharField(max_length=50)
    relay_name = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100)

class RelaySetting(models.Model):
    relay = models.ForeignKey(Relay, related_name='settings', on_delete=models.CASCADE)
    parameter_code = models.CharField(max_length=50)
    parameter_name = models.CharField(max_length=100)
    standard_value = models.FloatField()
    unit = models.CharField(max_length=20)
    tolerance_min = models.FloatField()
    tolerance_max = models.FloatField()
```

### 1.3 Phiếu Chỉnh định & Lịch sử
Sử dụng `JSONField` của PostgreSQL cho dữ liệu không cấu trúc, và tạo bảng rời cho chữ ký số để đảm bảo tính chuẩn hóa 3NF.

```python
class SettingSheet(models.Model):
    sheet_code = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=50) # DRAFT, PENDING_REVIEW, ASSIGNED, COMPLETED
    scan_file = models.FileField(upload_to='scans/')
    
    relay = models.ForeignKey(Relay, on_delete=models.SET_NULL, null=True)
    
    # OCR Data / Mock Data sử dụng JSONB của PostgreSQL
    extracted_data = models.JSONField(null=True, blank=True) 

class SignatureRecord(models.Model):
    sheet = models.ForeignKey(SettingSheet, related_name='signatures', on_delete=models.CASCADE)
    signer_name = models.CharField(max_length=100)
    role = models.CharField(max_length=50)
    signed_at = models.DateTimeField(auto_now_add=True)
    signature_hash = models.CharField(max_length=256)
```

### 1.4 Nhật ký Kiểm tra Định kỳ
```python
class PeriodicCheck(models.Model):
    relay = models.ForeignKey(Relay, on_delete=models.CASCADE)
    sheet = models.ForeignKey(SettingSheet, on_delete=models.CASCADE)
    scheduled_date = models.DateField()
    actual_check_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50)
    
class PeriodicCheckItem(models.Model):
    check = models.ForeignKey(PeriodicCheck, related_name='items', on_delete=models.CASCADE)
    parameter_code = models.CharField(max_length=50)
    measured_value = models.FloatField()
    deviation_percent = models.FloatField()
    is_within_tolerance = models.BooleanField()
```

## 2. Ưu điểm của Thiết kế này (PostgreSQL)
1. **Toàn vẹn Dữ liệu (ACID):** RDBMS như PostgreSQL đảm bảo tính nhất quán dữ liệu ở mức cao nhất, tránh mất mát thông tin quan trọng.
2. **Khả năng chứa dữ liệu động (extracted_data):** Tính năng `JSONField` (JSONB) của PostgreSQL cực kỳ tối ưu, cho phép lập chỉ mục (index) và truy vấn trên các trường bên trong file JSON (như kết quả OCR) mà không kém phần linh hoạt so với NoSQL.
3. **Mở rộng dễ dàng với ORM tiêu chuẩn:** Sử dụng 100% tính năng của Django ORM, dễ dàng viết các câu truy vấn phức tạp (Aggregation, Annotation), tích hợp tốt với các thư viện admin, form, và report của hệ sinh thái Django.
