from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging
from core.models import SystemConfig
from core.utils.api_sync import run_api_sync

logger = logging.getLogger(__name__)

@shared_task
def check_and_run_auto_sync():
    """
    Quét các cấu hình API có bật tự động đồng bộ.
    Kiểm tra nếu (bây giờ >= lần đồng bộ cuối + chu kỳ đồng bộ) thì tiến hành gọi API.
    """
    logger.info("Starting check_and_run_auto_sync...")
    now = timezone.now()
    
    # Lấy các cấu hình đang bật auto-sync
    configs = SystemConfig.objects.filter(auto_sync_enabled=True)
    
    for config in configs:
        should_run = False
        if not config.last_sync_time:
            # Chưa từng chạy
            should_run = True
        else:
            # Kiểm tra thời gian
            next_run_time = config.last_sync_time + timedelta(minutes=config.sync_interval_minutes)
            if now >= next_run_time:
                should_run = True
                
        if should_run:
            logger.info(f"Auto-sync triggered for {config.key}")
            
            # Set state to syncing
            config.is_syncing = True
            config.save(update_fields=['is_syncing'])
            
            try:
                # Thực thi đồng bộ
                success, count, err_msg = run_api_sync(config_id=config.id)
                
                # Cập nhật kết quả vào DB
                config.last_sync_time = timezone.now()
                config.sync_count += 1
                if success:
                    config.last_sync_status = f"Thành công ({count} bản ghi)"
                else:
                    config.last_sync_status = f"Thất bại: {err_msg[:50]}"
            finally:
                # Always clear the syncing state
                config.is_syncing = False
                config.save(update_fields=['last_sync_time', 'last_sync_status', 'sync_count', 'is_syncing'])
                
            logger.info(f"Auto-sync completed for {config.key}: {config.last_sync_status}")
            
    logger.info("Finished check_and_run_auto_sync.")
