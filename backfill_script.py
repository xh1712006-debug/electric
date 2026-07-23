import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from sheets.models import SettingSheet
from sheets.utils import update_has_parameters_changed_for_sheet

def run():
    sheets = SettingSheet.objects.all().order_by('created_at')
    updated = 0
    for sheet in sheets:
        if update_has_parameters_changed_for_sheet(sheet):
            updated += 1
    print(f"Processed {sheets.count()} sheets. Updated {updated} sheets with changes.")

if __name__ == '__main__':
    run()
