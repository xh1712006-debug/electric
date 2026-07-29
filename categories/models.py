from django.db import models

class CategoryBase(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="Mã")
    name = models.CharField(max_length=255, verbose_name="Tên")
    description = models.TextField(blank=True, null=True, verbose_name="Mô tả")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.code} - {self.name}"

class ManagementUnit(CategoryBase):
    sort_order = models.CharField(max_length=50, blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")
    parent_code = models.CharField(max_length=50, blank=True, null=True, verbose_name="Mã đơn vị cha (MA_DONVI_CHA)")
    unit_level = models.IntegerField(default=1, verbose_name="Cấp đơn vị (CAP_DONVI)")

    class Meta:
        verbose_name = "Đơn vị quản lý"
        verbose_name_plural = "Đơn vị quản lý"

class ManufacturingCountry(CategoryBase):
    legacy_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="Mã ID gốc (ID)")
    sort_order = models.CharField(max_length=50, blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")

    class Meta:
        verbose_name = "Nước sản xuất"
        verbose_name_plural = "Nước sản xuất"

class Manufacturer(CategoryBase):
    class Meta:
        verbose_name = "Hãng sản xuất"
        verbose_name_plural = "Hãng sản xuất"

class Ownership(CategoryBase):
    sort_order = models.CharField(max_length=50, blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")

    class Meta:
        verbose_name = "Sở hữu"
        verbose_name_plural = "Sở hữu"

class VoltageLevel(CategoryBase):
    legacy_code = models.CharField(max_length=50, blank=True, null=True, verbose_name="Mã phụ (MA)")
    sort_order = models.CharField(max_length=50, blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")

    class Meta:
        verbose_name = "Cấp điện áp"
        verbose_name_plural = "Cấp điện áp"

class EquipmentType(CategoryBase):
    class Meta:
        verbose_name = "Loại thiết bị"
        verbose_name_plural = "Loại thiết bị"

class OperationalStatus(CategoryBase):
    class Meta:
        verbose_name = "Trạng thái vận hành"
        verbose_name_plural = "Trạng thái vận hành"

class Line(CategoryBase):
    id_capda = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Cấp điện áp (ID_CAPDA)")
    id_ttvh = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Trạng thái vận hành (ID_TTVH)")
    da_tke = models.CharField(max_length=50, blank=True, null=True, verbose_name="Điện áp thiết kế (DA_TKE)")
    id_da_tke = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Điện áp thiết kế (ID_DA_TKE)")
    i_chophep = models.CharField(max_length=50, blank=True, null=True, verbose_name="Dòng điện cho phép (I_CHOPHEP)")
    
    ngay_vh = models.DateTimeField(blank=True, null=True, verbose_name="Ngày vận hành (NGAY_VH)")
    tong_cdai = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tổng chiều dài (TONG_CDAI)")
    so_mach = models.CharField(max_length=50, blank=True, null=True, verbose_name="Số mạch (SO_MACH)")
    id_dvi = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Đơn vị (ID_DVI)")
    id_sohuu = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Sở hữu (ID_SOHUU)")
    
    id_dz = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Đường dây (ID_DZ)")
    dz_cha = models.CharField(max_length=200, blank=True, null=True, verbose_name="Đường dây cha (DZ_CHA)")
    id_dz_cha = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Đường dây cha (ID_DZ_CHA)")
    
    id_tba_cap = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID TBA cấp (ID_TBA_CAP)")
    tba_cap = models.CharField(max_length=200, blank=True, null=True, verbose_name="TBA cấp (TBA_CAP)")
    id_nlo_cap = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Ngăn lộ cấp (ID_NLO_CAP)")
    nlo_cap = models.CharField(max_length=200, blank=True, null=True, verbose_name="Ngăn lộ cấp (NLO_CAP)")
    
    id_tba_nhan = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID TBA nhận (ID_TBA_NHAN)")
    tba_nhan = models.CharField(max_length=200, blank=True, null=True, verbose_name="TBA nhận (TBA_NHAN)")
    id_nlo_nhan = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Ngăn lộ nhận (ID_NLO_NHAN)")
    nlo_nhan = models.CharField(max_length=200, blank=True, null=True, verbose_name="Ngăn lộ nhận (NLO_NHAN)")
    
    sort_order = models.IntegerField(blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")

    class Meta:
        verbose_name = "Đường dây"
        verbose_name_plural = "Đường dây"

class Project(CategoryBase):
    id_ct = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Công trình (ID_CT)")
    id_capda = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Cấp điện áp (ID_CAPDA)")
    nam_xd = models.CharField(max_length=50, blank=True, null=True, verbose_name="Năm xây dựng (NAM_XD)")
    id_ttvh = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Trạng thái vận hành (ID_TTVH)")
    
    ma_ct_cha = models.CharField(max_length=100, blank=True, null=True, verbose_name="Mã Công trình cha (MA_CT_CHA)")
    ten_ct_cha = models.CharField(max_length=200, blank=True, null=True, verbose_name="Tên Công trình cha (TEN_CT_CHA)")
    
    id_sohuu = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Sở hữu (ID_SOHUU)")
    id_dvi = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Đơn vị (ID_DVI)")
    
    ngay_vh = models.DateTimeField(blank=True, null=True, verbose_name="Ngày vận hành (NGAY_VH)")
    sort_order = models.IntegerField(blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")

    class Meta:
        verbose_name = "Công trình"
        verbose_name_plural = "Công trình"

class Location(CategoryBase):
    id_vitri = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Vị trí (ID_VITRI)")
    id_capda = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Cấp điện áp (ID_CAPDA)")
    id_ttvh = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Trạng thái vận hành (ID_TTVH)")
    
    khoang_neo = models.CharField(max_length=100, blank=True, null=True, verbose_name="Khoảng néo (KHOANG_NEO)")
    khoang_cot = models.CharField(max_length=100, blank=True, null=True, verbose_name="Khoảng cột (KHOANG_COT)")
    
    id_khuvuc = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Khu vực (ID_KHUVUC)")
    khu_vuc = models.CharField(max_length=200, blank=True, null=True, verbose_name="Khu vực (KHU_VUC)")
    
    id_dvi = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Đơn vị (ID_DVI)")
    id_sohuu = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Sở hữu (ID_SOHUU)")
    
    id_ct = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Công trình (ID_CT)")
    ten_ct = models.CharField(max_length=200, blank=True, null=True, verbose_name="Tên Công trình (TEN_CT)")
    
    duong_vao = models.CharField(max_length=200, blank=True, null=True, verbose_name="Đường vào (DUONG_VAO)")
    hanh_lang = models.CharField(max_length=200, blank=True, null=True, verbose_name="Hành lang (HANH_LANG)")
    
    id_sodo = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID Sơ đồ (ID_SODO)")
    so_do = models.CharField(max_length=100, blank=True, null=True, verbose_name="Sơ đồ (SO_DO)")
    
    ngay_vh = models.DateTimeField(blank=True, null=True, verbose_name="Ngày vận hành (NGAY_VH)")
    sort_order = models.IntegerField(blank=True, null=True, verbose_name="Sắp xếp (SAPXEP)")

    class Meta:
        verbose_name = "Vị trí"
        verbose_name_plural = "Vị trí"
