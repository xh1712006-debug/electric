from sheets.models import SettingSheet
from django.db.models import Q
from django.core.cache import cache

def notification_badges(request):
    if not request.user.is_authenticated:
        return {'badges': {
            'pending_admin': 0, 'issued': 0, 'dispatcher_in_progress': 0,
            'routed': 0, 'station_in_progress': 0, 'station_pending_admin': 0,
            'supervisor_transferred': 0, 'supervisor_received': 0, 'supervisor_pending_admin': 0,
            'transferred': 0, 'technician_received': 0,
        }}
        
    user = request.user
    
    badges = {
        'pending_admin': 0, 'issued': 0, 'dispatcher_in_progress': 0,
        'routed': 0, 'station_in_progress': 0, 'station_pending_admin': 0,
        'supervisor_transferred': 0, 'supervisor_received': 0, 'supervisor_pending_admin': 0,
        'transferred': 0, 'technician_received': 0,
    }
    
    # 1. ADMIN - Chờ Duyệt Ban hành
    if user.is_superuser or user.groups.filter(name='ADMIN').exists():
        badges['pending_admin'] = SettingSheet.objects.filter(status='PENDING_ADMIN_APPROVAL').count()
        
    # 2. DISPATCHER
    if user.groups.filter(name='DISPATCHER').exists():
        base_qs = SettingSheet.objects.filter(created_by=user) if not user.is_superuser else SettingSheet.objects.all()
        badges['issued'] = base_qs.filter(status='ISSUED').count()
        badges['dispatcher_in_progress'] = base_qs.filter(status__in=['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED']).count()
        
    # 3. STATION_LEADER
    if user.groups.filter(name='STATION_LEADER').exists():
        if hasattr(user, 'userprofile') and user.userprofile.station:
            station = user.userprofile.station
            base_qs = SettingSheet.objects.filter(
                Q(station=station) | Q(relay__bay__station=station)
            ).distinct()
            
            badges['routed'] = base_qs.filter(status='ROUTED_TO_STATION').count()
            badges['station_in_progress'] = base_qs.filter(status__in=['TRANSFERRED', 'RECEIVED']).count()
            badges['station_pending_admin'] = base_qs.filter(status='PENDING_ADMIN_APPROVAL').count()
            
    # 4. SUPERVISOR
    if user.groups.filter(name='SUPERVISOR').exists():
        if hasattr(user, 'userprofile') and user.userprofile.station:
            station = user.userprofile.station
            base_qs = SettingSheet.objects.filter(
                Q(station=station) | Q(relay__bay__station=station)
            ).distinct()
            
            badges['supervisor_transferred'] = base_qs.filter(status='TRANSFERRED').count()
            badges['supervisor_received'] = base_qs.filter(status='RECEIVED').count()
            badges['supervisor_pending_admin'] = base_qs.filter(status='PENDING_ADMIN_APPROVAL').count()
        
    # 5. TECHNICIAN
    if user.groups.filter(name='TECHNICIAN').exists():
        base_qs = SettingSheet.objects.filter(assigned_to=user)
        badges['transferred'] = base_qs.filter(status='TRANSFERRED').count()
        badges['technician_received'] = base_qs.filter(status='RECEIVED').count()

    return {'badges': badges}
