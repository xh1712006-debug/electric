from django.db import models

class Station(models.Model):
    station_code = models.CharField(max_length=50, unique=True)
    station_name = models.CharField(max_length=200)
    location = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.station_code} - {self.station_name}"

class Bay(models.Model):
    station = models.ForeignKey(Station, related_name='bays', on_delete=models.CASCADE)
    bay_code = models.CharField(max_length=50)
    bay_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.bay_code} ({self.station.station_code})"

class Relay(models.Model):
    bay = models.ForeignKey(Bay, related_name='relays', on_delete=models.CASCADE)
    relay_code = models.CharField(max_length=50)
    relay_name = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.relay_code} - {self.relay_name}"
        
    @property
    def active_sheet(self):
        # Lấy phiếu hoàn thành (đang có hiệu lực) mới nhất
        completed = self.settingsheet_set.filter(status='COMPLETED').order_by('-created_at').first()
        return completed if completed else self.settingsheet_set.first()

class RelaySetting(models.Model):
    relay = models.ForeignKey(Relay, related_name='settings', on_delete=models.CASCADE)
    parameter_code = models.CharField(max_length=50)
    parameter_name = models.CharField(max_length=100)
    standard_value = models.FloatField()
    unit = models.CharField(max_length=20)
    tolerance_min = models.FloatField()
    tolerance_max = models.FloatField()

    def __str__(self):
        return f"{self.parameter_code}: {self.standard_value} {self.unit}"
