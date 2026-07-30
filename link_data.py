import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from stations.models import Station, Bay, Relay
from django.db import transaction

def run_linking():
    with transaction.atomic():
        # Link Bays to Stations
        bays = Bay.objects.filter(station__isnull=True).exclude(id_tba__isnull=True)
        bay_updates = []
        
        # Pre-cache stations
        station_map = {s.id_tba: s for s in Station.objects.exclude(id_tba__isnull=True) if s.id_tba}
        for bay in bays:
            if bay.id_tba in station_map:
                bay.station = station_map[bay.id_tba]
                bay_updates.append(bay)
                
        Bay.objects.bulk_update(bay_updates, ['station'])
        print(f"Linked {len(bay_updates)} Bays to Stations")

        # Link Relays to Bays
        relays = Relay.objects.filter(bay__isnull=True).exclude(id_vtri_dat__isnull=True)
        relay_updates = []
        
        # Pre-cache bays
        bay_map = {b.id_nlo: b for b in Bay.objects.exclude(id_nlo__isnull=True) if b.id_nlo}
        for relay in relays:
            if relay.id_vtri_dat in bay_map:
                relay.bay = bay_map[relay.id_vtri_dat]
                relay_updates.append(relay)
                
        Relay.objects.bulk_update(relay_updates, ['bay'])
        print(f"Linked {len(relay_updates)} Relays to Bays")

if __name__ == '__main__':
    run_linking()
