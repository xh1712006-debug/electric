from django.db import models

class Station(models.Model):
    station_code = models.CharField(max_length=50, unique=True, verbose_name="Mã (MA)")
    station_name = models.CharField(max_length=200, verbose_name="Tên (TEN)")
    location = models.CharField(max_length=255, blank=True, null=True)
    
    # Các trường bổ sung từ Danh mục Trạm
    id_tba = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID TBA (ID_TBA)")
    id_tinh = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Tỉnh (ID_TINH)")
    tinh = models.CharField(max_length=100, blank=True, null=True, verbose_name="Tỉnh (TINH)")
    id_quan = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Quận (ID_QUAN)")
    quan = models.CharField(max_length=100, blank=True, null=True, verbose_name="Quận (QUAN)")
    id_phuong = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Phường (ID_PHUONG)")
    phuong = models.CharField(max_length=100, blank=True, null=True, verbose_name="Phường (PHUONG)")
    
    id_capda = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Cấp điện áp (ID_CAPDA)")
    id_ttvh = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Trạng thái vận hành (ID_TTVH)")
    
    kieu_tram = models.CharField(max_length=100, blank=True, null=True, verbose_name="Kiểu trạm (KIEU_TRAM)")
    id_kieu_tram = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Kiểu trạm (ID_KIEU_TRAM)")
    
    loai_tram = models.CharField(max_length=100, blank=True, null=True, verbose_name="Loại trạm (LOAI_TRAM)")
    id_loai_tram = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Loại trạm (ID_LOAI_TRAM)")
    
    ngay_vh = models.DateTimeField(blank=True, null=True, verbose_name="Ngày vận hành (NGAY_VH)")
    ngay_ld = models.DateTimeField(blank=True, null=True, verbose_name="Ngày lắp đặt (NGAY_LD)")
    
    id_dvi = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Đơn vị (ID_DVI)")
    id_vung = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Vùng (ID_VUNG)")
    updated_at = models.DateTimeField(auto_now=True)
    vung = models.CharField(max_length=100, blank=True, null=True, verbose_name="Vùng (VUNG)")
    
    id_sohuu = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Sở hữu (ID_SOHUU)")
    
    kieu_ht_dk = models.CharField(max_length=100, blank=True, null=True, verbose_name="Kiểu HT ĐK (KIEU_HT_DK)")
    id_kieu_ht_dk = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Kiểu HT ĐK (ID_KIEU_HT_DK)")
    
    sort_order = models.IntegerField(blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")

    class Meta:
        verbose_name = "Danh mục Trạm"
        verbose_name_plural = "Danh mục Trạm"

    @property
    def code(self):
        return self.station_code

    @property
    def name(self):
        return self.station_name

    def __str__(self):
        return f"{self.station_code} - {self.station_name}"

class Bay(models.Model):
    station = models.ForeignKey(Station, related_name='bays', on_delete=models.CASCADE, null=True, blank=True)
    bay_code = models.CharField(max_length=50, verbose_name="Mã (MA)")
    bay_name = models.CharField(max_length=255, verbose_name="Tên (TEN)")
    
    # Các trường bổ sung từ Danh mục Ngăn lộ
    ten_tram = models.CharField(max_length=255, blank=True, null=True, verbose_name="Tên trạm (TEN_TRAM)")
    id_capda = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Cấp điện áp (ID_CAPDA)")
    id_ttvh = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Trạng thái vận hành (ID_TTVH)")
    ngay_vh = models.DateTimeField(blank=True, null=True, verbose_name="Ngày vận hành (NGAY_VH)")
    id_dvi = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Đơn vị (ID_DVI)")
    id_nlo = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Ngăn lộ (ID_NLO)")
    id_tba = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID TBA (ID_TBA)")
    id_sohuu = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Sở hữu (ID_SOHUU)")
    sort_order = models.IntegerField(blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")
    
    u_dm = models.CharField(max_length=50, blank=True, null=True, verbose_name="U_DM")
    i_dm = models.CharField(max_length=50, blank=True, null=True, verbose_name="I_DM")
    sdm = models.CharField(max_length=50, blank=True, null=True, verbose_name="SDM")

    updated_at = models.DateTimeField(auto_now=True)
    @property
    def code(self):
        return self.bay_code

    @property
    def name(self):
        return self.bay_name

    def __str__(self):
        return f"{self.bay_code} - {self.bay_name}"

class Relay(models.Model):
    bay = models.ForeignKey(Bay, related_name='relays', on_delete=models.CASCADE, null=True, blank=True)
    relay_code = models.CharField(max_length=50, verbose_name="Mã (MA)")
    relay_name = models.CharField(max_length=255, verbose_name="Tên (TEN)")
    manufacturer = models.CharField(max_length=100, blank=True, null=True)

    # Các trường bổ sung từ Danh mục Thiết bị (Rơ le)
    id_tbi = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Thiết bị (ID_TBI)")
    id_capda = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Cấp điện áp (ID_CAPDA)")
    id_ttvh = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Trạng thái vận hành (ID_TTVH)")
    id_hang_sx = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Hãng sản xuất (ID_HANG_SX)")
    id_nuoc_sx = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Nước sản xuất (ID_NUOC_SX)")
    
    id_loai_tb = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Loại thiết bị (ID_LOAI_TB)")
    id_loai_dt = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Loại đối tượng (ID_LOAI_DT)")
    id_doituong = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Đối tượng (ID_DOITUONG)")
    
    id_dvi = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Đơn vị (ID_DVI)")
    id_sohuu = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Sở hữu (ID_SOHUU)")
    
    id_vtri_dat = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Vị trí đặt (ID_VTRI_DAT)")
    ngay_vh = models.DateTimeField(blank=True, null=True, verbose_name="Ngày vận hành (NGAY_VH)")
    sort_order = models.IntegerField(blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")

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

    @property
    def code(self):
        return self.relay_code

    @property
    def name(self):
        return self.relay_name

    def __str__(self):
        return f"{self.relay_code} - {self.relay_name}"
        
    @property
    def active_sheet(self):
        # Lấy phiếu hoàn thành (đang có hiệu lực) mới nhất
        completed = self.settingsheet_set.filter(status='COMPLETED').order_by('-created_at').first()
        return completed if completed else self.settingsheet_set.first()
        
    updated_at = models.DateTimeField(auto_now=True)

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
