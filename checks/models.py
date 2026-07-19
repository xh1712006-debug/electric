from django.db import models
from stations.models import Relay
from sheets.models import SettingSheet

class PeriodicCheck(models.Model):
    STATUS_CHOICES = (
        ('SCHEDULED', 'Scheduled'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    )

    relay = models.ForeignKey(Relay, on_delete=models.CASCADE)
    sheet = models.ForeignKey(SettingSheet, on_delete=models.CASCADE, null=True, blank=True)
    scheduled_date = models.DateField()
    actual_check_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='SCHEDULED')

    def __str__(self):
        return f"Check for {self.relay.relay_code} on {self.scheduled_date}"

class PeriodicCheckItem(models.Model):
    periodic_check = models.ForeignKey(PeriodicCheck, related_name='items', on_delete=models.CASCADE)
    parameter_code = models.CharField(max_length=50)
    measured_value = models.FloatField()
    deviation_percent = models.FloatField()
    is_within_tolerance = models.BooleanField()

    def __str__(self):
        return f"{self.parameter_code}: {self.measured_value}"
