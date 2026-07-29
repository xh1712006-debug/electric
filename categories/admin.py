from django.contrib import admin
from .models import (
    ManagementUnit, ManufacturingCountry, Manufacturer, Ownership, 
    VoltageLevel, EquipmentType, OperationalStatus, Line, Project, 
    Location
)

admin.site.register(ManagementUnit)
admin.site.register(ManufacturingCountry)
admin.site.register(Manufacturer)
admin.site.register(Ownership)
admin.site.register(VoltageLevel)
admin.site.register(EquipmentType)
admin.site.register(OperationalStatus)
admin.site.register(Line)
admin.site.register(Project)
admin.site.register(Location)
