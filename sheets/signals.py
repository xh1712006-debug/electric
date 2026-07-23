from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import SettingSheet

def invalidate_sheet_cache(sender, instance, **kwargs):
    """
    Tự động tăng version cache khi có phiếu được thêm, sửa, hoặc xóa.
    Điều này làm vô hiệu hóa tất cả các cache cũ của danh sách phiếu,
    đảm bảo người dùng luôn thấy dữ liệu mới nhất.
    """
    try:
        cache.incr('sheet_list_version')
    except ValueError:
        # ValueError xảy ra khi key chưa tồn tại
        cache.set('sheet_list_version', 2)

@receiver(post_save, sender=SettingSheet)
def on_sheet_save(sender, instance, **kwargs):
    invalidate_sheet_cache(sender, instance, **kwargs)

@receiver(post_delete, sender=SettingSheet)
def on_sheet_delete(sender, instance, **kwargs):
    invalidate_sheet_cache(sender, instance, **kwargs)
