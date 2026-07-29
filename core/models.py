from django.db import models
from django.contrib.auth.models import User

class Organization(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    org_type = models.CharField(max_length=50) # VTC, OPERATION, TRANSMISSION...
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True)
    station = models.ForeignKey('stations.Station', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    phone_number = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return self.user.username

class SystemConfig(models.Model):
    key = models.CharField(max_length=100, unique=True, verbose_name="Mã cấu hình")
    value = models.CharField(max_length=500, verbose_name="Giá trị")
    description = models.TextField(blank=True, null=True, verbose_name="Mô tả")
    auth_header = models.CharField(max_length=500, blank=True, null=True, verbose_name="Token/Header xác thực")
    
    # Auto-sync settings
    auto_sync_enabled = models.BooleanField(default=False, verbose_name="Tự động đồng bộ")
    sync_interval_minutes = models.IntegerField(default=1440, verbose_name="Chu kỳ đồng bộ (phút)")
    last_sync_time = models.DateTimeField(null=True, blank=True, verbose_name="Lần đồng bộ cuối")
    last_sync_status = models.CharField(max_length=50, null=True, blank=True, verbose_name="Trạng thái đồng bộ cuối")
    sync_count = models.IntegerField(default=0, verbose_name="Số lần đồng bộ")
    is_syncing = models.BooleanField(default=False, verbose_name="Đang đồng bộ")
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.key}: {self.value}"
