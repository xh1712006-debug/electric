from django.apps import AppConfig
import threading
import time

def auto_revert_worker():
    from sheets.models import SettingSheet
    from django.utils import timezone
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    while True:
        try:
            now = timezone.now()
            expired_sheets = SettingSheet.objects.filter(
                is_temporary=True,
                status='COMPLETED',
                reverted=False,
                valid_until__lte=now,
                revert_to_sheet__isnull=False
            )
            
            channel_layer = get_channel_layer()

            for sheet in expired_sheets:
                # 1. Create a new revert sheet
                new_code = f"{sheet.sheet_code}-REV"
                counter = 1
                while SettingSheet.objects.filter(sheet_code=new_code).exists():
                    new_code = f"{sheet.sheet_code}-REV-{counter}"
                    counter += 1

                revert_sheet = SettingSheet.objects.create(
                    sheet_code=new_code,
                    title=f"Phục hồi cấu hình từ: {sheet.title}",
                    status='TRANSFERRED',
                    relay=sheet.relay,
                    created_by=sheet.created_by,
                    assigned_to=sheet.assigned_to,
                    supervisor_assigned=sheet.supervisor_assigned,
                    extracted_data=sheet.revert_to_sheet.extracted_data
                )
                
                # 2. Mark original sheet as reverted
                sheet.reverted = True
                sheet.save()
                
                # 3. Send notifications
                if channel_layer:
                    if revert_sheet.assigned_to:
                        async_to_sync(channel_layer.group_send)(
                            f"user_{revert_sheet.assigned_to.id}",
                            {
                                "type": "send_notification",
                                "title": "Phục hồi cấu hình Khẩn cấp",
                                "message": f"Cấu hình tạm thời của Rơ-le {sheet.relay.relay_code} đã hết hạn. Phiếu {new_code} đã được tạo tự động để thi công hoàn trả."
                            }
                        )
                    if revert_sheet.supervisor_assigned:
                        async_to_sync(channel_layer.group_send)(
                            f"user_{revert_sheet.supervisor_assigned.id}",
                            {
                                "type": "send_notification",
                                "title": "Giám sát phục hồi cấu hình",
                                "message": f"Phiếu tạm {sheet.sheet_code} đã hết hạn. Phiếu phục hồi {new_code} đã được tự động giao."
                            }
                        )
        except Exception as e:
            print("Auto-revert worker error:", e)
            
        time.sleep(30) # Run every 30 seconds

class SheetsConfig(AppConfig):
    name = 'sheets'

    def ready(self):
        import os
        # Prevent running the thread twice in development (reloader)
        if os.environ.get('RUN_MAIN', None) != 'true':
            return
            
        thread = threading.Thread(target=auto_revert_worker, daemon=True)
        thread.start()
