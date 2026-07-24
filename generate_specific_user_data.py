import os
import sys
import django
import random
import string
import hashlib
from datetime import timedelta
from django.utils import timezone

sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from django.contrib.auth.models import User, Group
from stations.models import Station, Bay, Relay
from core.models import UserProfile
from sheets.models import SettingSheet, SignatureRecord

def get_random_string(length):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_specific_data():
    print("=== BẮT ĐẦU TẠO DỮ LIỆU ĐÚNG LUỒNG KÝ SỐ ===")
    
    station, _ = Station.objects.get_or_create(
        station_code="TBA_MAIN",
        defaults={
            'station_name': "Trạm Biến Áp Chính",
            'location': "Khu vực Trung Tâm"
        }
    )
    bay, _ = Bay.objects.get_or_create(station=station, bay_code="NL_MAIN_1", defaults={'bay_name': 'Ngăn Lộ 1'})
    relay, _ = Relay.objects.get_or_create(bay=bay, relay_code="R_MAIN_1", defaults={'relay_name': 'Rơ le 1', 'manufacturer': 'ABB'})
    
    print("1. Đang cấu hình 5 tài khoản...")
    for g in ['DISPATCHER', 'STATION_LEADER', 'SUPERVISOR', 'TECHNICIAN']:
        Group.objects.get_or_create(name=g)
        
    users_data = [
        {'username': 'admin', 'password': 'admin', 'role': None, 'is_superuser': True, 'is_staff': True},
        {'username': 'dispatcher_1', 'password': '123456', 'role': 'DISPATCHER', 'is_superuser': False, 'is_staff': False},
        {'username': 'station_leader_1', 'password': '123456', 'role': 'STATION_LEADER', 'is_superuser': False, 'is_staff': False},
        {'username': 'supervisor_1', 'password': '123456', 'role': 'SUPERVISOR', 'is_superuser': False, 'is_staff': False},
        {'username': 'technician_1', 'password': '123456', 'role': 'TECHNICIAN', 'is_superuser': False, 'is_staff': False},
    ]
    
    created_users = {}
    
    for u_data in users_data:
        user, created = User.objects.get_or_create(username=u_data['username'])
        user.set_password(u_data['password'])
        user.is_superuser = u_data['is_superuser']
        user.is_staff = u_data['is_staff']
        user.first_name = u_data['username'].replace('_', ' ').title()
        user.save()
        
        if u_data['role']:
            group = Group.objects.get(name=u_data['role'])
            user.groups.add(group)
            if u_data['role'] != 'DISPATCHER':
                UserProfile.objects.update_or_create(user=user, defaults={'station': station})
            else:
                UserProfile.objects.update_or_create(user=user, defaults={'station': None})
                
        created_users[u_data['username']] = user
        
    print("=> Hoàn tất tạo 5 tài khoản.")
    
    print("2. Đang dọn dẹp phiếu cũ và tạo phiếu mới với đầy đủ lịch sử ký số...")
    
    admin = created_users['admin']
    dispatcher = created_users['dispatcher_1']
    technician = created_users['technician_1']
    supervisor = created_users['supervisor_1']
    
    statuses = [s[0] for s in SettingSheet.STATUS_CHOICES]
    
    param_templates = []
    for p in range(1, 11):
        param_templates.append({
            'parameter_code': f'P_{p}',
            'parameter_name': f'Thông số {p}',
            'unit': random.choice(['A', 'V', 's', 'Hz']),
        })
        
    SettingSheet.objects.filter(sheet_code__startswith='MAINTEST-').delete()
    
    sheets_to_create = []
    
    for i in range(100):
        status = random.choice(statuses)
        
        assignee = technician if status in ['TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED'] else None
        supv = supervisor if status in ['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED'] else None
        
        mock_data = []
        for template in param_templates:
            mock_data.append({
                'parameter_code': template['parameter_code'],
                'parameter_name': template['parameter_name'],
                'unit': template['unit'],
                'value': round(random.uniform(5.0, 200.0), 2),
                'confidence': round(random.uniform(95.0, 99.9), 1)
            })
            
        base_time = timezone.now() - timedelta(days=random.randint(0, 60), hours=random.randint(0, 24))
        
        sheet = SettingSheet(
            sheet_code=f'MAINTEST-{get_random_string(5)}-{i}',
            title=f'Phiếu Test Chính {i}',
            status=status,
            created_by=dispatcher,
            assigned_to=assignee,
            supervisor_assigned=supv,
            relay=relay,
            station=station,
            scan_file='scans/mock_scan.pdf',
            extracted_data=mock_data
        )
        # Gán created_at thủ công trước, sau đó sẽ update lại do auto_now_add
        sheet._base_time = base_time
        if assignee:
            sheet.assigned_at = base_time + timedelta(hours=1)
            
        sheets_to_create.append(sheet)

    print("  Đang lưu SettingSheets (bulk_create)...")
    SettingSheet.objects.bulk_create(sheets_to_create, batch_size=100)
    
    # Reload để có id cho SignatureRecord
    created_sheets = list(SettingSheet.objects.filter(sheet_code__startswith='MAINTEST-'))
    
    # Cập nhật created_at
    for s in created_sheets:
        # Match với base_time dựa trên list ban đầu
        for sc in sheets_to_create:
            if sc.sheet_code == s.sheet_code:
                s.created_at = sc._base_time
                break
    SettingSheet.objects.bulk_update(created_sheets, ['created_at'], batch_size=100)

    # Chạy lại list sau khi update created_at
    created_sheets = list(SettingSheet.objects.filter(sheet_code__startswith='MAINTEST-'))

    def make_hash(s, role):
        return hashlib.sha256(f"{s.id}-{role}-{s.created_at}".encode('utf-8')).hexdigest()

    signatures_to_create = []
    for sheet in created_sheets:
        base_time = sheet.created_at
        
        if sheet.status in ['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            signatures_to_create.append(SignatureRecord(
                sheet=sheet, signer_name=dispatcher.first_name, role='DISPATCHER',
                signature_hash=make_hash(sheet, 'DISPATCHER')
            ))
            
        # Đối với RECEIVED, ta cho 50% số phiếu đã được KTV ký (nhưng Giám sát chưa ký) để Giám sát có thể test
        technician_signed = False
        if sheet.status in ['PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            technician_signed = True
        elif sheet.status == 'RECEIVED' and random.choice([True, False]):
            technician_signed = True
            
        if technician_signed:
            signatures_to_create.append(SignatureRecord(
                sheet=sheet, signer_name=technician.first_name, role='TECHNICIAN',
                signature_hash=make_hash(sheet, 'TECHNICIAN')
            ))
            
        if sheet.status in ['PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            signatures_to_create.append(SignatureRecord(
                sheet=sheet, signer_name=supervisor.first_name, role='SUPERVISOR',
                signature_hash=make_hash(sheet, 'SUPERVISOR')
            ))
            
        if sheet.status == 'COMPLETED':
            signatures_to_create.append(SignatureRecord(
                sheet=sheet, signer_name=admin.first_name, role='ADMIN',
                signature_hash=make_hash(sheet, 'ADMIN')
            ))
            
    print("  Đang tạo dữ liệu Ký Số (bulk_create)...")
    SignatureRecord.objects.bulk_create(signatures_to_create, batch_size=100)
    
    # Vì auto_now_add tự sinh signed_at, ta cần update lại thời gian chuẩn luồng
    print("  Khôi phục thời gian ký số chuẩn luồng...")
    created_sigs = list(SignatureRecord.objects.select_related('sheet').filter(sheet__sheet_code__startswith='MAINTEST-'))
    for sig in created_sigs:
        if sig.role == 'DISPATCHER':
            sig.signed_at = sig.sheet.created_at + timedelta(minutes=30)
        elif sig.role == 'TECHNICIAN':
            sig.signed_at = sig.sheet.created_at + timedelta(hours=2)
        elif sig.role == 'SUPERVISOR':
            sig.signed_at = sig.sheet.created_at + timedelta(hours=3)
        elif sig.role == 'ADMIN':
            sig.signed_at = sig.sheet.created_at + timedelta(hours=4)
            
    SignatureRecord.objects.bulk_update(created_sigs, ['signed_at'], batch_size=100)
    
    # Xoá cache của Django để UI cập nhật ngay lập tức do bulk_create không kích hoạt tín hiệu (signals)
    from django.core.cache import cache
    cache.clear()
        
    print("=> Hoàn tất tạo phiếu và chữ ký chuẩn luồng.")
    print("=== DỮ LIỆU ĐÃ SẴN SÀNG ===")

if __name__ == "__main__":
    generate_specific_data()
