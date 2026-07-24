import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rms_project.settings")
django.setup()

from stations.models import Relay
from django.test import Client

client = Client()

relay = Relay.objects.first()
if relay:
    print(f"Testing relay {relay.id}")
    # We need to bypass login or simulate it
    from django.contrib.auth.models import User
    admin = User.objects.filter(is_superuser=True).first()
    client.force_login(admin)
    
    response = client.post(f'/stations/relay/{relay.id}/update_schedule/', {
        'enabled': 'on',
        'schedule_mode': 'exact',
        'exact_datetime': '2026-07-23T23:27',
    })
    
    print(response.status_code)
    if response.status_code == 500:
        print("ERROR 500:", response.content.decode())
    else:
        print("SUCCESS:", response.content.decode()[:200])
