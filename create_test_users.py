import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from django.contrib.auth.models import User, Group
from stations.models import Station
from core.models import UserProfile

def setup_test_users():
    print("Setting up test users for quick login...")
    
    roles = {
        'dispatcher_1': ('DISPATCHER', 'Kỹ sư Điều độ Demo'),
        'station_leader_1': ('STATION_LEADER', 'Trưởng trạm Demo'),
        'supervisor_1': ('SUPERVISOR', 'Giám sát viên Demo'),
        'technician_1': ('TECHNICIAN', 'Kỹ thuật viên Demo'),
    }
    
    # Ensure groups exist
    for group_name in ['ADMIN', 'DISPATCHER', 'STATION_LEADER', 'SUPERVISOR', 'TECHNICIAN']:
        Group.objects.get_or_create(name=group_name)

    # Get a default station if any exists
    station = Station.objects.first()
        
    for username, (group_name, full_name) in roles.items():
        user, created = User.objects.get_or_create(username=username)
        user.set_password('123456')
        user.first_name = full_name
        user.save()
        
        # Assign to group
        group = Group.objects.get(name=group_name)
        user.groups.add(group)
        
        # Ensure UserProfile exists
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = group_name
        profile.full_name = full_name
        if station and group_name in ['STATION_LEADER', 'TECHNICIAN', 'SUPERVISOR']:
            profile.station = station
        profile.save()
        
        print(f"{'Created' if created else 'Updated'} user {username} in group {group_name}")

    print("Test users setup complete!")

if __name__ == '__main__':
    setup_test_users()
