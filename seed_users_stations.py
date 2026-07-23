import os
import django
import random
import string

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from django.contrib.auth.models import User, Group
from stations.models import Station, Bay, Relay
from core.models import UserProfile

def get_random_string(length):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def seed_infrastructure_and_users():
    print("Bắt đầu tạo dữ liệu Trạm, Rơ-le và Người dùng...")

    # 1. Generate 20 Stations
    stations = []
    for i in range(1, 21):
        station_code = f"TBA_{random.randint(110, 500)}_{get_random_string(3)}"
        station, created = Station.objects.get_or_create(
            station_code=station_code,
            defaults={
                'station_name': f"Trạm Biến Áp {station_code}",
                'location': f"Khu vực {i}"
            }
        )
        stations.append(station)
        
        # For each station, create 3 bays
        for j in range(1, 4):
            bay, _ = Bay.objects.get_or_create(
                station=station,
                bay_code=f"Ngan_Lo_{j}",
                defaults={'bay_name': f"Ngăn lộ {j} - {station.station_code}"}
            )
            
            # For each bay, create 2 relays
            for k in range(1, 3):
                Relay.objects.get_or_create(
                    bay=bay,
                    relay_code=f"F{k}_{bay.bay_code}",
                    defaults={
                        'relay_name': f"Rơ-le bảo vệ {k}",
                        'manufacturer': random.choice(['Siemens', 'ABB', 'SEL', 'GE', 'Schneider'])
                    }
                )
    print(f"Đã tạo {len(stations)} Trạm và các Ngăn Lộ, Rơ-le tương ứng.")

    # 2. Generate Users
    groups = ['DISPATCHER', 'STATION_LEADER', 'SUPERVISOR', 'TECHNICIAN']
    for group_name in groups:
        Group.objects.get_or_create(name=group_name)

    roles_count = {
        'DISPATCHER': 5,
        'STATION_LEADER': 15,
        'SUPERVISOR': 15,
        'TECHNICIAN': 30
    }

    user_count = 0
    for role, count in roles_count.items():
        group = Group.objects.get(name=role)
        for i in range(count):
            username = f"{role.lower()}_{i+1}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': f"{role.replace('_', ' ').title()} {i+1}",
                    'email': f"{username}@evn.com.vn"
                }
            )
            if created:
                user.set_password('123456')
                user.save()
            
            user.groups.add(group)
            
            # Assign to random station (except dispatcher)
            station = None
            if role != 'DISPATCHER':
                station = random.choice(stations)
                
            UserProfile.objects.update_or_create(
                user=user,
                defaults={'station': station}
            )
            user_count += 1

    print(f"Đã tạo {user_count} người dùng (mật khẩu mặc định: 123456).")
    print("HOÀN TẤT TẠO HẠ TẦNG VÀ NGƯỜI DÙNG!")

seed_infrastructure_and_users()
