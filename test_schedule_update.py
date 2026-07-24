import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from stations.models import Relay
from django.contrib.auth import get_user_model
from django.test import Client

client = Client()
User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
if user:
    client.force_login(user)

relay1 = Relay.objects.first()
relay2 = Relay.objects.last()

print(f"Testing POST to relay {relay1.relay_code}")
response = client.post(f'/stations/relay/{relay1.id}/update_schedule/', {
    'enabled': 'on',
    'schedule_mode': 'interval',
    'interval_value': 1,
    'interval_unit': 'h'
})
print(f"POST Response status: {response.status_code}")
print(f"HX-Trigger header: {response.get('HX-Trigger')}")

print(f"Testing GET to relay {relay2.relay_code}")
response2 = client.get(f'/stations/relay/{relay2.id}/update_schedule/')
print(f"GET Response status: {response2.status_code}")
print(f"GET Response length: {len(response2.content)}")
