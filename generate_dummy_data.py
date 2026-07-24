import os
import sys
import django
import random
import string
from datetime import timedelta
from django.utils import timezone

sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from django.contrib.auth.models import User, Group
from django.contrib.auth.hashers import make_password
from stations.models import Station, Bay, Relay
from core.models import UserProfile
from sheets.models import SettingSheet

def get_random_string(length):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_large_test_data():
    print("=== BẮT ĐẦU TẠO DỮ LIỆU LỚN CHO MỤC ĐÍCH TEST ===")
    
    # 1. Tạo 10 Trạm mới (Stations)
    print("1. Đang tạo thêm 10 Trạm, Ngăn lộ và Rơ-le...")
    new_stations = []
    for i in range(1, 11):
        station_code = f"TBA_DUMMY_{random.randint(1000, 9999)}_{get_random_string(3)}"
        station, _ = Station.objects.get_or_create(
            station_code=station_code,
            defaults={
                'station_name': f"Trạm Biến Áp Dummy {station_code}",
                'location': f"Khu vực Dummy {i}"
            }
        )
        new_stations.append(station)
        
        for j in range(1, 4):
            bay, _ = Bay.objects.get_or_create(
                station=station,
                bay_code=f"NL_DUMMY_{j}_{get_random_string(2)}",
                defaults={'bay_name': f"Ngăn lộ Dummy {j} - {station.station_code}"}
            )
            for k in range(1, 3):
                Relay.objects.get_or_create(
                    bay=bay,
                    relay_code=f"R_DUMMY_{k}_{bay.bay_code}",
                    defaults={
                        'relay_name': f"Rơ-le Dummy {k}",
                        'manufacturer': random.choice(['Siemens', 'ABB', 'SEL', 'GE', 'Schneider'])
                    }
                )
    print("=> Hoàn tất tạo 10 Trạm mới.")

    all_stations = list(Station.objects.all())

    # 2. Tạo 400 Tài khoản (Users)
    print("2. Đang tạo 400 Tài khoản (Accounts)...")
    groups = ['DISPATCHER', 'STATION_LEADER', 'SUPERVISOR', 'TECHNICIAN']
    for group_name in groups:
        Group.objects.get_or_create(name=group_name)
        
    roles_count = {
        'DISPATCHER': 50,
        'STATION_LEADER': 50,
        'SUPERVISOR': 100,
        'TECHNICIAN': 200
    }
    
    users_to_create = []
    user_roles = [] # để lưu mapping username -> role group
    password_hash = make_password('123456')
    
    # Chuẩn bị user instances
    for role, count in roles_count.items():
        for i in range(count):
            username = f"{role.lower()}_dummy_{get_random_string(4)}_{i}"
            users_to_create.append(User(
                username=username,
                first_name=f"{role.replace('_', ' ').title()} Dummy {i}",
                email=f"{username}@evn.dummy.vn",
                password=password_hash
            ))
            user_roles.append((username, role))
            
    # Xoá users cũ nếu trùng
    usernames = [u.username for u in users_to_create]
    User.objects.filter(username__in=usernames).delete()
    
    # Bulk create users
    print("  Đang insert users...")
    User.objects.bulk_create(users_to_create, batch_size=100)
    
    # Lấy lại danh sách users đã tạo
    created_users_dict = {u.username: u for u in User.objects.filter(username__in=usernames)}
    
    # Gán group và UserProfile
    print("  Đang gán role và profile...")
    profiles_to_create = []
    
    UserGroup = User.groups.through
    user_groups_to_create = []
    groups_dict = {g.name: g for g in Group.objects.all()}
    
    for username, role in user_roles:
        u = created_users_dict.get(username)
        if u:
            # Prepare user-group map
            user_groups_to_create.append(UserGroup(user_id=u.id, group_id=groups_dict[role].id))
            
            # Prepare profile map
            station = None if role == 'DISPATCHER' else random.choice(all_stations)
            profiles_to_create.append(UserProfile(user=u, station=station))
            
    UserGroup.objects.bulk_create(user_groups_to_create, batch_size=100)
    UserProfile.objects.bulk_create(profiles_to_create, batch_size=100)
            
    print(f"=> Hoàn tất tạo 400 Tài khoản mới (mật khẩu mặc định: 123456).")

    # 3. Tạo 2000 Phiếu (SettingSheets) với > 60 thông số
    print("3. Đang tạo 2000 Phiếu với mỗi phiếu 65 thông số...")
    
    all_relays = list(Relay.objects.all())
    dispatchers = list(User.objects.filter(groups__name='DISPATCHER'))
    supervisors = list(User.objects.filter(groups__name='SUPERVISOR'))
    technicians = list(User.objects.filter(groups__name='TECHNICIAN'))
    
    statuses = [s[0] for s in SettingSheet.STATUS_CHOICES]
    
    param_templates = []
    for p in range(1, 66):
        param_templates.append({
            'parameter_code': f'PARAM_{p}',
            'parameter_name': f'Thông số Dummy {p}',
            'unit': random.choice(['A', 'V', 's', 'Hz', 'Ohm']),
        })
        
    sheets_to_create = []
    for i in range(2000):
        station = random.choice(all_stations)
        relay = random.choice(all_relays) if all_relays else None
        dispatcher = random.choice(dispatchers) if dispatchers else None
        
        status = random.choice(statuses)
        assigned_to = random.choice(technicians) if technicians and status in ['TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED'] else None
        supervisor = random.choice(supervisors) if supervisors and status in ['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED'] else None
        
        mock_data = []
        for template in param_templates:
            mock_data.append({
                'parameter_code': template['parameter_code'],
                'parameter_name': template['parameter_name'],
                'unit': template['unit'],
                'value': round(random.uniform(1.0, 500.0), 2),
                'confidence': round(random.uniform(90.0, 99.9), 1)
            })
            
        sheet = SettingSheet(
            sheet_code=f'DUMMY-{get_random_string(6)}-{i}',
            title=f'Phiếu Dữ liệu Ảo {i}',
            status=status,
            created_by=dispatcher,
            assigned_to=assigned_to,
            supervisor_assigned=supervisor,
            relay=relay,
            station=station,
            scan_file='scans/mock_scan.pdf',
            extracted_data=mock_data
        )
        sheets_to_create.append(sheet)
        
        if (i + 1) % 500 == 0:
            print(f"  Đã chuẩn bị {i + 1} phiếu...")
            
    print("  Đang lưu vào cơ sở dữ liệu (bulk_create)...")
    SettingSheet.objects.bulk_create(sheets_to_create, batch_size=500)
    
    # Cập nhật created_at ngẫu nhiên
    print("  Đang cập nhật created_at ngẫu nhiên...")
    created_sheets = list(SettingSheet.objects.filter(sheet_code__startswith='DUMMY-'))
    
    for s in created_sheets:
        random_days = random.randint(0, 365)
        random_hours = random.randint(0, 24)
        s.created_at = timezone.now() - timedelta(days=random_days, hours=random_hours)

    SettingSheet.objects.bulk_update(created_sheets, ['created_at'], batch_size=500)
    
    print("=> Hoàn tất tạo 2000 Phiếu.")
    print("=== DỮ LIỆU ĐÃ ĐƯỢC TẠO XONG ===")
    print(f"Tổng số phiếu trong hệ thống: {SettingSheet.objects.count()}")

if __name__ == "__main__":
    generate_large_test_data()
