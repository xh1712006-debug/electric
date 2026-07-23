import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from stations.models import Relay
from stations.api_mock import compare_and_log_relay_check

class Command(BaseCommand):
    help = 'Tiến trình ngầm kiểm tra Rơ-le tự động dựa trên lịch hẹn giờ độc lập'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Bắt đầu chạy tiến trình kiểm tra Rơ-le thông minh... (Bấm Ctrl+C để dừng)"))
        self.stdout.write("Hệ thống sẽ quét mỗi 5 giây để tìm các Rơ-le đến hẹn.")
        
        while True:
            now = timezone.now()
            
            from django.db.models import Q
            relays = Relay.objects.filter(
                settingsheet__isnull=False, 
                auto_check_enabled=True
            ).filter(
                Q(next_check_at__isnull=True) | Q(next_check_at__lte=now)
            ).distinct()
            
            for relay in relays:
                log = compare_and_log_relay_check(relay)
                if log:
                    if log.status == 'MISMATCH':
                        msg = self.style.ERROR(f"[{log.checked_at.strftime('%H:%M:%S')}] {relay.relay_code}: PHÁT HIỆN SAI LỆCH!")
                    else:
                        msg = self.style.SUCCESS(f"[{log.checked_at.strftime('%H:%M:%S')}] {relay.relay_code}: Bình thường.")
                    self.stdout.write(msg)
                    
                    # Tính toán giờ chạy tiếp theo
                    relay.last_checked_at = log.checked_at
                    relay.next_check_at = relay.calculate_next_check(log.checked_at)
                    relay.save(update_fields=['last_checked_at', 'next_check_at'])
            
            time.sleep(5)
