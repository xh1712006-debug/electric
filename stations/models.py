from django.db import models

class Station(models.Model):
    station_code = models.CharField(max_length=50, unique=True)
    station_name = models.CharField(max_length=200)
    location = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.station_code} - {self.station_name}"

class Bay(models.Model):
    station = models.ForeignKey(Station, related_name='bays', on_delete=models.CASCADE)
    bay_code = models.CharField(max_length=50)
    bay_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.bay_code} ({self.station.station_code})"

class Relay(models.Model):
    bay = models.ForeignKey(Bay, related_name='relays', on_delete=models.CASCADE)
    relay_code = models.CharField(max_length=50)
    relay_name = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100)

    # Lịch trình tự động kiểm tra API
    UNIT_CHOICES = [
        ('s', 'Giây'),
        ('m', 'Phút'),
        ('h', 'Giờ'),
        ('d', 'Ngày'),
        ('M', 'Tháng'),
        ('y', 'Năm'),
        ('e', 'Cụ thể (1 lần)'),
    ]
    auto_check_enabled = models.BooleanField(default=False, db_index=True)
    check_interval_value = models.IntegerField(default=1)
    check_interval_unit = models.CharField(max_length=1, choices=UNIT_CHOICES, default='h')
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    # Workflow fields
    is_paused_for_correction = models.BooleanField(default=False, db_index=True)
    paused_schedule_data = models.JSONField(null=True, blank=True)

    def calculate_next_check(self, from_time=None):
        import datetime
        import calendar
        from django.utils import timezone
        if not from_time:
            from_time = timezone.now()
            
        val = self.check_interval_value
        unit = self.check_interval_unit
        
        if unit == 'e':
            return None # Chế độ 1 lần không tự tính toán chu kỳ lặp lại
            
        if unit == 's':
            return from_time + datetime.timedelta(seconds=val)
        elif unit == 'm':
            return from_time + datetime.timedelta(minutes=val)
        elif unit == 'h':
            return from_time + datetime.timedelta(hours=val)
        elif unit == 'd':
            return from_time + datetime.timedelta(days=val)
        elif unit == 'M':
            month = from_time.month - 1 + val
            year = from_time.year + month // 12
            month = month % 12 + 1
            day = min(from_time.day, calendar.monthrange(year, month)[1])
            return from_time.replace(year=year, month=month, day=day)
        elif unit == 'y':
            try:
                return from_time.replace(year=from_time.year + val)
            except ValueError:
                return from_time.replace(year=from_time.year + val, day=28)
        
        return from_time + datetime.timedelta(hours=1)

    def __str__(self):
        return f"{self.relay_code} - {self.relay_name}"
        
    @property
    def active_sheet(self):
        # Lấy phiếu hoàn thành (đang có hiệu lực) mới nhất
        completed = self.settingsheet_set.filter(status='COMPLETED').order_by('-created_at').first()
        return completed if completed else self.settingsheet_set.first()

class RelaySetting(models.Model):
    relay = models.ForeignKey(Relay, related_name='settings', on_delete=models.CASCADE)
    parameter_code = models.CharField(max_length=50)
    parameter_name = models.CharField(max_length=100)
    standard_value = models.FloatField()
    unit = models.CharField(max_length=20)
    tolerance_min = models.FloatField()
    tolerance_max = models.FloatField()

    def __str__(self):
        return f"{self.parameter_code}: {self.standard_value} {self.unit}"

class RelayAutoCheckLog(models.Model):
    STATUS_CHOICES = [
        ('MATCH', 'Trùng khớp'),
        ('MISMATCH', 'Có sai lệch'),
        ('API_ERROR', 'Lỗi kết nối API'),
    ]
    relay = models.ForeignKey(Relay, related_name='auto_checks', on_delete=models.CASCADE)
    checked_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='MATCH')
    api_raw_data = models.JSONField(null=True, blank=True)
    differences = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-checked_at']

    def __str__(self):
        return f"Check {self.relay.relay_code} at {self.checked_at.strftime('%d/%m/%Y %H:%M:%S')}"

class CorrectionTicket(models.Model):
    STATUS_CHOICES = [
        ('DISPATCHER', 'Phân phối viên xử lý'),
        ('STATION', 'Trạm xử lý'),
        ('TECH', 'Kỹ thuật viên xử lý'),
        ('SUPERVISOR', 'Giám sát ký'),
        ('ADMIN', 'Admin ký duyệt'),
        ('RESOLVED', 'Hoàn tất'),
    ]
    relay = models.ForeignKey(Relay, related_name='correction_tickets', on_delete=models.CASCADE)
    log = models.ForeignKey(RelayAutoCheckLog, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DISPATCHER')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def current_step_idx(self):
        flow = ['DISPATCHER', 'STATION', 'TECH', 'SUPERVISOR', 'ADMIN', 'RESOLVED']
        try:
            return flow.index(self.status)
        except ValueError:
            return 0
            
    def get_flow_steps(self):
        return [
            ('DISPATCHER', 'Phân phối', 0),
            ('STATION', 'Trạm', 1),
            ('TECH', 'Kỹ thuật', 2),
            ('SUPERVISOR', 'Giám sát', 3),
            ('ADMIN', 'Admin', 4),
        ]

class TicketSignature(models.Model):
    ticket = models.ForeignKey(CorrectionTicket, related_name='signatures', on_delete=models.CASCADE)
    signer_name = models.CharField(max_length=100)
    role = models.CharField(max_length=50)
    signed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    signature_hash = models.CharField(max_length=256)

    class Meta:
        ordering = ['signed_at']
