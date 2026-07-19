import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rms_project.settings")
django.setup()

from django.contrib.auth.models import Group

# The user mentioned they merged REVIEWER and DISPATCHER. 
# We will delete the REVIEWER group so it no longer shows in the matrix.
Group.objects.filter(name='REVIEWER').delete()

print("Deleted REVIEWER group.")
