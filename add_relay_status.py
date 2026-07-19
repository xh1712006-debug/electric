with open('d:/project/dien-luc/stations/views.py', 'a', encoding='utf-8') as f:
    f.write('''

@login_required
def relay_status_dashboard(request):
    """Bảng điều khiển theo dõi tiến độ cấu hình rơ-le"""
    # Tất cả rơ-le
    total_relays = Relay.objects.count()
    
    # Rơ-le đã có phiếu
    configured_relays = Relay.objects.filter(settingsheet__isnull=False).distinct().select_related('bay', 'bay__station')
    configured_count = configured_relays.count()
    
    # Rơ-le chưa có phiếu
    unconfigured_relays = Relay.objects.filter(settingsheet__isnull=True).select_related('bay', 'bay__station')
    unconfigured_count = total_relays - configured_count
    
    # Phần trăm
    progress_percent = int((configured_count / total_relays * 100) if total_relays > 0 else 0)
    
    context = {
        'total_relays': total_relays,
        'configured_count': configured_count,
        'unconfigured_count': unconfigured_count,
        'progress_percent': progress_percent,
        'configured_relays': configured_relays,
        'unconfigured_relays': unconfigured_relays
    }
    
    return render(request, 'stations/relay_status.html', context)
''')
