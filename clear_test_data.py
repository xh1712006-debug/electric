import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from categories.models import *
from stations.models import *
from sheets.models import *
from core.models import Organization, SystemConfig

print("Deleting sheets...")
SignatureRecord.objects.all().delete()
SettingSheet.objects.all().delete()

print("Deleting stations...")
TicketSignature.objects.all().delete()
CorrectionTicket.objects.all().delete()
RelayAutoCheckLog.objects.all().delete()
RelaySetting.objects.all().delete()
Relay.objects.all().delete()
Bay.objects.all().delete()
Station.objects.all().delete()

print("Deleting categories...")
ManagementUnit.objects.all().delete()
ManufacturingCountry.objects.all().delete()
Manufacturer.objects.all().delete()
Ownership.objects.all().delete()
VoltageLevel.objects.all().delete()
EquipmentType.objects.all().delete()
OperationalStatus.objects.all().delete()
Line.objects.all().delete()
Project.objects.all().delete()
Location.objects.all().delete()

print("Deleting core (Organization)...")
Organization.objects.all().delete()

print("Data cleared successfully. Users and SystemConfig are kept.")
