from django.apps import AppConfig
from django.db.models.signals import post_migrate

def create_default_groups(sender, **kwargs):
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType
    
    # We must ensure models are loaded, so we get the content type from the app registry
    try:
        from sheets.models import SettingSheet
        content_type = ContentType.objects.get_for_model(SettingSheet)
    except Exception:
        return

    matrix = {
        'DISPATCHER': ['can_view_stations', 'can_create_sheet', 'can_dispatch_sheet'],
        'STATION_LEADER': ['can_view_stations', 'can_dispatch_sheet'],
        'TECHNICIAN': ['can_execute_sheet'],
        'SUPERVISOR': ['can_supervise_sheet'],
        'ADMIN': [
            'can_view_stations', 'can_manage_users', 'can_create_sheet', 
            'can_approve_sheet', 'can_dispatch_sheet', 'can_execute_sheet', 
            'can_supervise_sheet'
        ]
    }

    for group_name, perms in matrix.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        # Chỉ gán quyền mặc định nếu nhóm chưa có quyền nào (lần đầu khởi tạo)
        if not group.permissions.exists():
            for perm_codename in perms:
                try:
                    perm = Permission.objects.get(codename=perm_codename, content_type=content_type)
                    group.permissions.add(perm)
                except Permission.DoesNotExist:
                    pass

class CoreConfig(AppConfig):
    name = 'core'
    
    def ready(self):
        post_migrate.connect(create_default_groups, sender=self)
