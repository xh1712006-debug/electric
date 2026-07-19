import random
from django.core.management.base import BaseCommand
from core.models import Organization, UserProfile
from stations.models import Station, Bay, Relay, RelaySetting
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Seeds the database with initial sample data'

    def handle(self, *args, **kwargs):
        self.stdout.write("Bắt đầu khởi tạo dữ liệu mẫu...")

        # 1. Tạo Users và Organizations
        org_vtc, _ = Organization.objects.get_or_create(code="VTC_1", defaults={"name": "Công ty Truyền tải điện 1", "org_type": "TRANSMISSION"})
        org_station, _ = Organization.objects.get_or_create(code="TBA_HB", defaults={"name": "TBA 220kV Hòa Bình", "org_type": "STATION", "parent": org_vtc})

        user_a0, _ = User.objects.get_or_create(username="a0_admin", defaults={"email": "a0@evn.com.vn", "first_name": "A0", "last_name": "Admin"})
        if not hasattr(user_a0, 'userprofile'):
            user_a0.set_password("password123")
            user_a0.save()
            UserProfile.objects.create(user=user_a0, organization=org_vtc, phone_number="0988000111")

        # 2. Tạo Trạm biến áp (Station)
        station, _ = Station.objects.get_or_create(
            station_code="TBA_220KV_HB",
            defaults={
                "station_name": "Trạm biến áp 220kV Hòa Bình",
                "location": "Tỉnh Hòa Bình"
            }
        )

        # 3. Tạo Ngăn lộ (Bay)
        bays = []
        for i in range(1, 4):
            bay, _ = Bay.objects.get_or_create(
                station=station,
                bay_code=f"BAY_AT{i}",
                defaults={"bay_name": f"Ngăn Máy biến áp AT{i}"}
            )
            bays.append(bay)

        # 4. Tạo Rơ-le (Relay) và Cài đặt (RelaySetting)
        relay_count = 0
        for bay in bays:
            for j in range(1, 3):
                relay, created = Relay.objects.get_or_create(
                    bay=bay,
                    relay_code=f"REL_{bay.bay_code}_{j}",
                    defaults={
                        "relay_name": f"Rơ-le bảo vệ số {j} ({bay.bay_name})",
                        "manufacturer": random.choice(["ABB", "Siemens", "SEL", "GE"])
                    }
                )
                if created:
                    relay_count += 1
                    # Tạo settings chuẩn cho Relay
                    RelaySetting.objects.create(relay=relay, parameter_code="I_START", parameter_name="Dòng khởi động", standard_value=1.5, unit="A", tolerance_min=1.45, tolerance_max=1.55)
                    RelaySetting.objects.create(relay=relay, parameter_code="T_TRIP", parameter_name="Thời gian cắt", standard_value=0.5, unit="s", tolerance_min=0.48, tolerance_max=0.52)
                    RelaySetting.objects.create(relay=relay, parameter_code="V_MIN", parameter_name="Điện áp thấp", standard_value=100.0, unit="V", tolerance_min=98.0, tolerance_max=102.0)

        self.stdout.write(self.style.SUCCESS(f"Đã tạo thành công: 1 Trạm, {len(bays)} Ngăn lộ, {relay_count} Rơ-le."))
        self.stdout.write(self.style.SUCCESS("Hoàn tất sinh dữ liệu mẫu!"))
