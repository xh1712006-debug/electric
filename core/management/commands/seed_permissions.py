from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from sheets.models import SettingSheet

class Command(BaseCommand):
    help = 'Assign default permissions to groups'

    def handle(self, *args, **kwargs):
        content_type = ContentType.objects.get_for_model(SettingSheet)
        
        # Matrix mapping
        matrix = {
            'A0A1': ['can_view_stations', 'can_create_sheet'],
            'REVIEWER': ['can_approve_sheet'],
            'DISPATCHER': ['can_dispatch_sheet'],
            'TECHNICIAN': ['can_execute_sheet'],
            'SUPERVISOR': ['can_supervise_sheet'],
            'ADMIN': ['can_view_stations', 'can_manage_users', 'can_create_sheet', 'can_approve_sheet', 'can_dispatch_sheet', 'can_execute_sheet', 'can_supervise_sheet']
        }

        for group_name, perms in matrix.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.clear()
            for perm_codename in perms:
                try:
                    perm = Permission.objects.get(codename=perm_codename, content_type=content_type)
                    group.permissions.add(perm)
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"Permission {perm_codename} not found!"))
            
            self.stdout.write(self.style.SUCCESS(f"Assigned permissions to {group_name}"))

        self.stdout.write(self.style.SUCCESS('Successfully seeded default permissions!'))
