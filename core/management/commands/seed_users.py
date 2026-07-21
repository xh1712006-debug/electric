from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group

class Command(BaseCommand):
    help = 'Seed initial roles (groups) and dummy users for testing'

    def handle(self, *args, **kwargs):
        roles = [
            ('ADMIN', 'admin@evn.vn', 'Quản trị viên'),
            ('A0A1', 'a0@evn.vn', 'Điều độ viên A0/A1'),
            ('DISPATCHER', 'dispatcher@evn.vn', 'Người Điều phối'),
            ('STATION_LEADER', 'truongnhom@evn.vn', 'Trưởng nhóm Trạm'),
            ('TECHNICIAN', 'ktv@evn.vn', 'KTV Chỉnh định'),
            ('SUPERVISOR', 'truongtram@evn.vn', 'Giám sát Trạm')
        ]

        for role_name, email, full_name in roles:
            # Create Group
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created group: {role_name}"))

            # Create User
            username = email.split('@')[0]
            user, u_created = User.objects.get_or_create(username=username, defaults={
                'email': email,
                'first_name': full_name
            })
            
            if u_created:
                user.set_password('123456')
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created user: {username} (Password: 123456)"))
            
            # Assign user to group
            if not user.groups.filter(name=role_name).exists():
                user.groups.add(group)
                self.stdout.write(self.style.SUCCESS(f"Assigned {username} to {role_name}"))

            # Give admin user superuser status
            if role_name == 'ADMIN' and not user.is_superuser:
                user.is_superuser = True
                user.is_staff = True
                user.save()

        self.stdout.write(self.style.SUCCESS('Successfully seeded users and roles!'))
