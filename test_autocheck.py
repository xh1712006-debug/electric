import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from stations.models import Relay
from stations.api_mock import compare_and_log_relay_check

relay = Relay.objects.first()
print(f"Testing relay: {relay.relay_code}")

try:
    log = compare_and_log_relay_check(relay)
    print(f"Success! Status: {log.status}")
except Exception as e:
    import traceback
    traceback.print_exc()
