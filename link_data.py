import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms.settings')
django.setup()

from stations.models import Station, Bay, Relay

print("--- BẮT ĐẦU ĐỒNG BỘ DỮ LIỆU ---")

# 1. Nối Ngăn Lộ (Bay) vào Trạm (Station)
orphaned_bays = Bay.objects.filter(station__isnull=True)
bay_count = orphaned_bays.count()
print(f"Tìm thấy {bay_count} Ngăn lộ chưa được nối với Trạm.")

bays_linked = 0
for bay in orphaned_bays:
    if bay.id_tba:
        station = Station.objects.filter(id_tba=bay.id_tba).first()
        if station:
            bay.station = station
            bay.save(update_fields=['station'])
            bays_linked += 1

print(f"Đã nối thành công {bays_linked}/{bay_count} Ngăn lộ vào Trạm.")

# 2. Nối Rơ-le (Relay) vào Ngăn Lộ (Bay)
orphaned_relays = Relay.objects.filter(bay__isnull=True)
relay_count = orphaned_relays.count()
print(f"Tìm thấy {relay_count} Rơ-le chưa được nối với Ngăn lộ.")

relays_linked = 0
for relay in orphaned_relays:
    if relay.id_vtri_dat:
        bay = Bay.objects.filter(id_nlo=relay.id_vtri_dat).first()
        if bay:
            relay.bay = bay
            relay.save(update_fields=['bay'])
            relays_linked += 1

print(f"Đã nối thành công {relays_linked}/{relay_count} Rơ-le vào Ngăn lộ.")
print("--- HOÀN TẤT ---")
