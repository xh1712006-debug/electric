import re

with open('d:/project/dien-luc/stations/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add Q to imports if not there
if 'from django.db.models import Q' not in content:
    content = content.replace('from .models import Station, Bay, Relay', 'from .models import Station, Bay, Relay\nfrom django.db.models import Q')

# Rewrite station_list
new_station_list = '''@login_required
def station_list(request):
    q = request.GET.get('q', '').strip()
    
    if q:
        stations = Station.objects.prefetch_related('bays__relays__settingsheet_set').filter(
            Q(station_code__icontains=q) | 
            Q(station_name__icontains=q) |
            Q(bays__bay_code__icontains=q) |
            Q(bays__bay_name__icontains=q) |
            Q(bays__relays__relay_code__icontains=q) |
            Q(bays__relays__relay_name__icontains=q)
        ).distinct()
        is_search = True
    else:
        stations = Station.objects.all()
        is_search = False

    return render(request, 'stations/station_list.html', {
        'stations': stations,
        'q': q,
        'is_search': is_search
    })'''

old_func_pattern = re.compile(r'@login_required\ndef station_list\(request\):.*?(?=@login_required|\Z)', re.DOTALL)
content = old_func_pattern.sub(new_station_list + '\n\n', content, count=1)

# Append new views
new_views = '''
@login_required
def get_bays_htmx(request, station_id):
    station = get_object_or_404(Station, pk=station_id)
    bays = station.bays.all()
    return render(request, 'stations/partials/bay_list.html', {'bays': bays, 'station': station})

@login_required
def get_relays_htmx(request, bay_id):
    bay = get_object_or_404(Bay, pk=bay_id)
    relays = bay.relays.prefetch_related('settingsheet_set').all()
    return render(request, 'stations/partials/relay_list.html', {'relays': relays, 'bay': bay})

@login_required
def search_suggestions(request):
    q = request.GET.get('q', '').strip()
    suggestions = []
    if q and len(q) >= 1:
        st = Station.objects.filter(Q(station_code__icontains=q) | Q(station_name__icontains=q))[:3]
        for s in st: suggestions.append(s.station_code)
        
        by = Bay.objects.filter(Q(bay_code__icontains=q) | Q(bay_name__icontains=q))[:3]
        for b in by: suggestions.append(b.bay_code)
        
        rl = Relay.objects.filter(Q(relay_code__icontains=q) | Q(relay_name__icontains=q))[:5]
        for r in rl: suggestions.append(r.relay_code)
        
    return render(request, 'stations/partials/suggestions.html', {'suggestions': suggestions})
'''

content += new_views

with open('d:/project/dien-luc/stations/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
