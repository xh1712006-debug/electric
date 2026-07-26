from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import random
import time
import uuid

@shared_task
def execute_bulk_create_task(idempotency_key, user_id, sheet_ids):
    from sheets.models import SettingSheet
    from django.contrib.auth.models import User
    from sheets.views import perform_mock_ocr
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        cache.set(idempotency_key, {'status': 'ERROR', 'message': 'User not found'}, timeout=86400)
        return

    success_count = 0
    failed_count = 0
    
    channel_layer = get_channel_layer()

    for sheet_id in sheet_ids:
        try:
            sheet = SettingSheet.objects.get(id=sheet_id)
            file_name = sheet.title
            
            # Gửi thông báo đang bắt đầu xử lý file này
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        "type": "bulk_progress",
                        "event_type": "bulk_progress",
                        "idempotency_key": idempotency_key,
                        "sheet_id": sheet_id,
                        "file_name": file_name,
                        "status": "processing"
                    }
                )

            # Perform OCR on the uploaded file
            perform_mock_ocr(sheet)
            # Update status to ISSUED (Chờ rà soát)
            sheet.status = 'ISSUED'
            sheet.save(update_fields=['status'])
            success_count += 1
            # Simulate OCR processing delay
            time.sleep(2)
            
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        "type": "bulk_progress",
                        "event_type": "bulk_progress",
                        "idempotency_key": idempotency_key,
                        "sheet_id": sheet_id,
                        "file_name": file_name,
                        "status": "success",
                        "processed_count": success_count + failed_count,
                        "total": len(sheet_ids)
                    }
                )
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        "type": "bulk_progress",
                        "event_type": "update_badges"
                    }
                )
        except Exception as e:
            failed_count += 1
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        "type": "send_notification",
                        "event_type": "bulk_progress",
                        "idempotency_key": idempotency_key,
                        "sheet_id": sheet_id,
                        "status": "failed",
                        "processed_count": success_count + failed_count,
                        "total": len(sheet_ids)
                    }
                )

    result_data = {
        'status': 'COMPLETED',
        'total_requested': len(sheet_ids),
        'success': success_count,
        'failed': failed_count,
        'finished_at': timezone.now().isoformat()
    }

    # Lưu kết quả vào Redis giữ trong 24h
    cache.set(idempotency_key, result_data, timeout=86400)
    
    # Gửi thông báo WebSocket tới User
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "send_notification",
                "title": "Trích xuất Hàng loạt Hoàn tất",
                "message": f"Đã xử lý xong {len(sheet_ids)} file. Thành công: {success_count}, Thất bại: {failed_count}.",
                "level": "success" if failed_count == 0 else "warning"
            }
        )
