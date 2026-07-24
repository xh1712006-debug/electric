import os
import django
import random
import hashlib
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from django.contrib.auth.models import User, Group
from stations.models import Station, Relay, Bay
from sheets.models import SettingSheet, SignatureRecord

def create_mock_data():
    # 1. Get some users
    try:
        admin_user = User.objects.get(username='admin')
        dispatcher = User.objects.filter(groups__name='DISPATCHER').first() or admin_user
        station_leader = User.objects.filter(groups__name='STATION_LEADER').first() or admin_user
        technician = User.objects.filter(groups__name='TECHNICIAN').first() or admin_user
        supervisor = User.objects.filter(groups__name='SUPERVISOR').first() or admin_user
    except Exception:
        admin_user = User.objects.filter(is_superuser=True).first()
        dispatcher = station_leader = technician = supervisor = admin_user

    # 2. Get some relays
    relays = list(Relay.objects.all()[:10])
    if not relays:
        print("Không có Relay nào trong DB. Vui lòng tạo Relay trước.")
        return

    print("Đang xóa dữ liệu cũ...")
    SettingSheet.objects.all().delete()
    
    statuses = [
        ('DRAFT', "Nháp"),
        ('ISSUED', "Chờ Rà soát"),
        ('ROUTED_TO_STATION', "Đã chuyển về Trạm (Đã rà soát)"),
        ('TRANSFERRED', "Đã giao KTV"),
        ('RECEIVED', "Đang thực hiện"),
        ('PENDING_ADMIN_APPROVAL', "Chờ duyệt ban hành (Đã thi công xong)"),
        ('COMPLETED', "Hoàn thành")
    ]
    
    now = timezone.now()
    
    print("Đang tạo Phiếu Chỉnh Định (Setting Sheets) mới...")
    
    for i in range(1, 15):
        relay = random.choice(relays)
        status, desc = statuses[i % len(statuses)]
        
        sheet = SettingSheet.objects.create(
            sheet_code=f"PCD-{now.strftime('%Y%m%d')}-{i:03d}",
            title=f"Phiếu chỉnh định rơ-le {relay.relay_name} ({desc})",
            status=status,
            created_by=dispatcher,
            relay=relay,
            station=relay.bay.station if relay.bay else None,
            created_at=now - timedelta(days=random.randint(1, 10)),
            extracted_data={"I>": "1.5", "t>": "0.5"}
        )
        
        # Add workflow specific data based on status
        if status in ['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            # Has been issued & signed for review
            SignatureRecord.objects.create(
                sheet=sheet,
                signer_name=dispatcher.get_full_name() or dispatcher.username,
                role='Kỹ sư Điều độ',
                signed_at=sheet.created_at + timedelta(hours=1),
                signature_hash=hashlib.sha256(f"{sheet.id}DISPATCHER".encode()).hexdigest()
            )
            
        if status in ['TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            # Assigned to tech
            sheet.assigned_to = technician
            sheet.supervisor_assigned = supervisor
            sheet.assigned_at = sheet.created_at + timedelta(hours=2)
            sheet.save()
            
        if status in ['PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            # Execution signed
            SignatureRecord.objects.create(
                sheet=sheet,
                signer_name=technician.get_full_name() or technician.username,
                role='Kỹ thuật viên',
                signed_at=sheet.created_at + timedelta(hours=24),
                signature_hash=hashlib.sha256(f"{sheet.id}TECH".encode()).hexdigest()
            )
            SignatureRecord.objects.create(
                sheet=sheet,
                signer_name=supervisor.get_full_name() or supervisor.username,
                role='Giám sát viên',
                signed_at=sheet.created_at + timedelta(hours=25),
                signature_hash=hashlib.sha256(f"{sheet.id}SUP".encode()).hexdigest()
            )
            
        if status == 'COMPLETED':
            # Final approval
            SignatureRecord.objects.create(
                sheet=sheet,
                signer_name=admin_user.get_full_name() or admin_user.username,
                role='Trưởng ban Điều độ',
                signed_at=sheet.created_at + timedelta(hours=26),
                signature_hash=hashlib.sha256(f"{sheet.id}ADMIN".encode()).hexdigest()
            )

    print("Tạo dữ liệu hoàn tất!")

if __name__ == '__main__':
    create_mock_data()
