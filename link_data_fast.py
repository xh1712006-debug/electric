from stations.models import Station, Bay, Relay

print("--- BẮT ĐẦU ĐỒNG BỘ DỮ LIỆU TỐC ĐỘ CAO ---")

# Preload stations and bays into dictionaries for O(1) lookup
print("Đang nạp dữ liệu vào bộ nhớ...")
stations = {s.id_tba: s for s in Station.objects.exclude(id_tba__isnull=True).exclude(id_tba='')}
bays_dict = {b.id_nlo: b for b in Bay.objects.exclude(id_nlo__isnull=True).exclude(id_nlo='')}

# 1. Update Bays
orphaned_bays = list(Bay.objects.filter(station__isnull=True))
print(f"Tìm thấy {len(orphaned_bays)} Ngăn lộ chưa được nối với Trạm.")

bays_to_update = []
for bay in orphaned_bays:
    if bay.id_tba and bay.id_tba in stations:
        bay.station = stations[bay.id_tba]
        bays_to_update.append(bay)

if bays_to_update:
    print(f"Đang lưu {len(bays_to_update)} bản ghi vào DB...")
    Bay.objects.bulk_update(bays_to_update, ['station'], batch_size=1000)
print(f"Đã nối thành công {len(bays_to_update)} Ngăn lộ vào Trạm.")

# 2. Update Relays
orphaned_relays = list(Relay.objects.filter(bay__isnull=True))
print(f"Tìm thấy {len(orphaned_relays)} Rơ-le chưa được nối với Ngăn lộ.")

relays_to_update = []
for relay in orphaned_relays:
    if relay.id_vtri_dat and relay.id_vtri_dat in bays_dict:
        relay.bay = bays_dict[relay.id_vtri_dat]
        relays_to_update.append(relay)

if relays_to_update:
    print(f"Đang lưu {len(relays_to_update)} bản ghi vào DB...")
    Relay.objects.bulk_update(relays_to_update, ['bay'], batch_size=1000)
print(f"Đã nối thành công {len(relays_to_update)} Rơ-le vào Ngăn lộ.")

print("--- HOÀN TẤT ---")
