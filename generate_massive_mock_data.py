import os
import django
import random
import hashlib
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from django.contrib.auth.models import User, Group
from core.models import UserProfile
from stations.models import Station, Bay, Relay
from sheets.models import SettingSheet, SignatureRecord
from django.core.cache import cache

def generate_data():
    print("Clearing old data...")
    SignatureRecord.objects.all().delete()
    SettingSheet.objects.all().delete()
    UserProfile.objects.all().delete()
    Relay.objects.all().delete()
    Bay.objects.all().delete()
    Station.objects.all().delete()
    User.objects.exclude(is_superuser=True).delete()

    print("Generating 100 Stations...")
    stations = []
    for i in range(1, 101):
        stations.append(Station(
            station_code=f"ST-{i:03d}",
            station_name=f"Trạm biến áp {i:03d}kV",
            location=f"Khu vực {random.choice(['Bắc', 'Trung', 'Nam'])}"
        ))
    Station.objects.bulk_create(stations)
    stations = list(Station.objects.all())

    print("Generating Bays and Relays...")
    bays = []
    for station in stations:
        for j in range(random.randint(2, 4)):
            bays.append(Bay(
                station=station,
                bay_code=f"{station.station_code}-B{j:02d}",
                bay_name=f"Ngăn lộ {j:02d}"
            ))
    Bay.objects.bulk_create(bays)
    bays = list(Bay.objects.all())

    relays = []
    for bay in bays:
        for k in range(random.randint(2, 3)):
            relays.append(Relay(
                bay=bay,
                relay_code=f"{bay.bay_code}-R{k:02d}",
                relay_name=f"Rơ-le {k:02d}",
                manufacturer=random.choice(["Siemens", "ABB", "SEL", "GE"]),
                auto_check_enabled=True,
                check_interval_value=random.randint(1, 6),
                check_interval_unit='M'
            ))
    Relay.objects.bulk_create(relays)
    relays = list(Relay.objects.all())

    print("Generating 200 Users...")
    group_roles = ['ADMIN', 'DISPATCHER', 'STATION_LEADER', 'SUPERVISOR', 'TECHNICIAN']
    
    users = []
    for i in range(1, 201):
        role = random.choice(group_roles)
        username = f"{role.lower()}_{i:03d}"
        users.append(User(
            username=username,
            email=f"{username}@evn.com.vn",
            first_name=f"Test {role} {i}",
            is_active=True
        ))
    
    for u in users:
        u.set_password("123456")
        
    User.objects.bulk_create(users)
    
    users = list(User.objects.exclude(is_superuser=True))
    profiles = []
    
    groups = {g.name: g for g in Group.objects.all()}
    
    for u in users:
        role = u.username.split('_')[0].upper()
        if role in groups:
            u.groups.add(groups[role])
            
        if role in ['STATION_LEADER', 'SUPERVISOR', 'TECHNICIAN']:
            profiles.append(UserProfile(
                user=u,
                station=random.choice(stations)
            ))
            
    UserProfile.objects.bulk_create(profiles)
    
    dispatchers = [u for u in users if u.username.startswith('dispatcher')]
    if not dispatchers:
        print("Warning: No dispatchers created.")
        return
        
    admin_users = [u for u in users if u.username.startswith('admin')] or User.objects.filter(is_superuser=True)
    
    station_techs = {}
    station_supers = {}
    for p in profiles:
        u = p.user
        role = u.username.split('_')[0].upper()
        if role == 'TECHNICIAN':
            station_techs.setdefault(p.station_id, []).append(u)
        elif role == 'SUPERVISOR':
            station_supers.setdefault(p.station_id, []).append(u)

    print("Generating 2000 Setting Sheets...")
    now = timezone.now()
    sheets = []
    signatures_to_create = []
    
    statuses = [
        'DRAFT', 'ISSUED', 'ROUTED_TO_STATION', 
        'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED'
    ]
    
    param_pool = []
    for p in range(1, 101):
        param_pool.append({
            "parameter_code": f"PARAM_{p:03d}",
            "parameter_name": f"Thông số {p}",
            "unit": random.choice(["A", "V", "s", "Hz", "Ohm", ""]),
        })

    for i in range(1, 2001):
        relay = random.choice(relays)
        station = relay.bay.station
        
        status = random.choice(statuses)
        dispatcher = random.choice(dispatchers)
        
        num_params = random.randint(60, 100)
        selected_params = random.sample(param_pool, num_params)
        extracted_data = []
        for p in selected_params:
            val = round(random.uniform(0.1, 100.0), 2)
            extracted_data.append({
                "parameter_code": p["parameter_code"],
                "parameter_name": p["parameter_name"],
                "unit": p["unit"],
                "value": str(val),
                "original_value": str(val),
                "confidence": round(random.uniform(90.0, 99.9), 1)
            })
            
        sheet = SettingSheet(
            sheet_code=f"PCD-{now.strftime('%Y%m%d')}-{i:04d}",
            title=f"Phiếu chỉnh định rơ-le {relay.relay_name} (Auto {i})",
            status=status,
            created_by=dispatcher,
            relay=relay,
            station=station,
            created_at=now - timedelta(days=random.randint(1, 30)),
            extracted_data=extracted_data
        )
        
        if status in ['TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            techs = station_techs.get(station.id, [])
            if techs:
                sheet.assigned_to = random.choice(techs)
                sheet.assigned_at = sheet.created_at + timedelta(hours=2)
                
            supers = station_supers.get(station.id, [])
            if supers:
                sheet.supervisor_assigned = random.choice(supers)

        sheets.append(sheet)

    print("Bulk creating SettingSheets (this may take a moment)...")
    SettingSheet.objects.bulk_create(sheets, batch_size=500)
    
    sheets = list(SettingSheet.objects.all())
    
    print("Generating Signatures...")
    for sheet in sheets:
        if sheet.status == 'DRAFT':
            continue
            
        signatures_to_create.append(SignatureRecord(
            sheet=sheet, signer_name=sheet.created_by.first_name, role="Điều độ viên", 
            signed_at=sheet.created_at + timedelta(hours=1), signature_hash=hashlib.md5(b"sig").hexdigest()
        ))
        
        if sheet.status in ['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            admin = random.choice(admin_users) if admin_users else sheet.created_by
            signatures_to_create.append(SignatureRecord(
                sheet=sheet, signer_name=admin.first_name, role="Quản trị viên (Chuyển trạm)", 
                signed_at=sheet.created_at + timedelta(hours=2), signature_hash=hashlib.md5(b"sig").hexdigest()
            ))
            
        if sheet.status in ['PENDING_ADMIN_APPROVAL', 'COMPLETED']:
            if sheet.assigned_to:
                signatures_to_create.append(SignatureRecord(
                    sheet=sheet, signer_name=sheet.assigned_to.first_name, role="Kỹ thuật viên", 
                    signed_at=sheet.created_at + timedelta(hours=4), signature_hash=hashlib.md5(b"sig").hexdigest()
                ))
            if sheet.supervisor_assigned:
                signatures_to_create.append(SignatureRecord(
                    sheet=sheet, signer_name=sheet.supervisor_assigned.first_name, role="Giám sát trạm", 
                    signed_at=sheet.created_at + timedelta(hours=5), signature_hash=hashlib.md5(b"sig").hexdigest()
                ))
                
        if sheet.status == 'COMPLETED':
            admin = random.choice(admin_users) if admin_users else sheet.created_by
            signatures_to_create.append(SignatureRecord(
                sheet=sheet, signer_name=admin.first_name, role="Quản trị viên (Phê duyệt)", 
                signed_at=sheet.created_at + timedelta(hours=6), signature_hash=hashlib.md5(b"sig").hexdigest()
            ))

    print("Bulk creating Signatures...")
    SignatureRecord.objects.bulk_create(signatures_to_create, batch_size=5000)
    
    cache.set('sheet_list_version', int(now.timestamp()))
    print("DONE! Massive mock data generation complete.")

if __name__ == '__main__':
    with transaction.atomic():
        generate_data()
