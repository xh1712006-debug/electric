from rest_framework import serializers
from .models import (
    ManagementUnit, ManufacturingCountry, Manufacturer, Ownership,
    VoltageLevel, EquipmentType, OperationalStatus, Line, Project, Location
)
from stations.models import Station, Bay, Relay

# Generic serializer for all CategoryBase models
class CategoryBaseSerializer(serializers.ModelSerializer):
    class Meta:
        fields = '__all__'

def create_serializer(model_class):
    class Meta:
        model = model_class
        fields = '__all__'
    
    return type(f'{model_class.__name__}Serializer', (CategoryBaseSerializer,), {'Meta': Meta})

ManagementUnitSerializer = create_serializer(ManagementUnit)
ManufacturingCountrySerializer = create_serializer(ManufacturingCountry)
ManufacturerSerializer = create_serializer(Manufacturer)
OwnershipSerializer = create_serializer(Ownership)
VoltageLevelSerializer = create_serializer(VoltageLevel)
EquipmentTypeSerializer = create_serializer(EquipmentType)
OperationalStatusSerializer = create_serializer(OperationalStatus)
LineSerializer = create_serializer(Line)
ProjectSerializer = create_serializer(Project)
LocationSerializer = create_serializer(Location)

# Serializers for existing Station, Bay, Relay to match the format somewhat
class StationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Station
        fields = '__all__'

class BaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Bay
        fields = '__all__'

class RelaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Relay
        fields = '__all__'
