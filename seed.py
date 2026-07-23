import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

import random
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User

def seed_data(count=2000):
    from sheets.models import SettingSheet
    from stations.models import Station, Relay

    print(f"Bắt đầu tạo {count} phiếu dữ liệu mẫu để test chịu tải...")
    
    stations = list(Station.objects.all())
    relays = list(Relay.objects.all())
    
    if not stations or not relays:
        print("Lỗi: Không tìm thấy Trạm hoặc Rơ-le trong DB.")
        return

    dispatchers = list(User.objects.filter(groups__name='DISPATCHER'))
    supervisors = list(User.objects.filter(groups__name='SUPERVISOR'))
    technicians = list(User.objects.filter(groups__name='TECHNICIAN'))

    if not dispatchers:
        print("Lỗi: Không có tài khoản Dispatcher.")
        return

    statuses = [s[0] for s in SettingSheet.STATUS_CHOICES]
    
    for i in range(count):
        station = random.choice(stations)
        relay = random.choice(relays)
        dispatcher = random.choice(dispatchers)
        
        status = random.choices(
            statuses, 
            weights=[5, 10, 15, 15, 20, 15, 20] # Phân bổ trọng số ngẫu nhiên
        )[0]
        
        assigned_to = random.choice(technicians) if technicians and status in ['TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED'] else None
        supervisor = random.choice(supervisors) if supervisors and status in ['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED'] else None
        
        created_at = timezone.now() - timedelta(days=random.randint(0, 365), hours=random.randint(0, 24))
        
        sheet = SettingSheet(
            sheet_code=f'TEST-{random.randint(100000, 999999)}-{i}',
            title=f'Phiếu kiểm thử tải dữ liệu {i}',
            status=status,
            created_by=dispatcher,
            assigned_to=assigned_to,
            supervisor_assigned=supervisor,
            relay=relay,
            station=station,
            scan_file='scans/mock_scan.pdf'
        )
        
        mock_data = [
            {'parameter_code': 'I_max', 'parameter_name': 'Dòng cắt cực đại', 'unit': 'A', 'value': round(random.uniform(10, 100), 2), 'confidence': 98.0},
            {'parameter_code': 'T_delay', 'parameter_name': 'Thời gian trễ', 'unit': 's', 'value': round(random.uniform(0.1, 2.0), 2), 'confidence': 99.0}
        ]
        sheet.extracted_data = mock_data
        
        sheet.save()
        # Chỉnh sửa lại thời gian tạo giả (vì auto_now_add sẽ ghi đè lúc save)
        SettingSheet.objects.filter(id=sheet.id).update(created_at=created_at)
        
        if (i + 1) % 500 == 0:
            print(f"Đã tạo {i + 1} phiếu...")

    print("===============================")
    print("HOÀN TẤT TẠO DỮ LIỆU!")
    print(f"Tổng số phiếu trong hệ thống hiện tại: {SettingSheet.objects.count()}")

seed_data(2000)
