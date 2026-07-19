from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from .models import PeriodicCheck, PeriodicCheckItem
from stations.models import Relay, RelaySetting
from datetime import datetime
import json

@login_required
def check_list(request):
    """View danh sách lịch kiểm tra định kỳ."""
    checks = PeriodicCheck.objects.all().order_by('-scheduled_date')
    return render(request, 'checks/check_list.html', {'checks': checks})

@login_required
def check_create(request):
    """View tạo lịch kiểm tra mới."""
    if request.method == 'POST':
        relay_id = request.POST.get('relay_id')
        scheduled_date = request.POST.get('scheduled_date')
        
        relay = get_object_or_404(Relay, pk=relay_id)
        
        # Tạo Check mới
        check = PeriodicCheck.objects.create(
            relay=relay,
            scheduled_date=scheduled_date,
            status='SCHEDULED'
        )
        
        # Load các thông số từ RelaySetting để tạo các Item trống
        settings = RelaySetting.objects.filter(relay=relay)
        for s in settings:
            PeriodicCheckItem.objects.create(
                periodic_check=check,
                parameter_code=s.parameter_code,
                measured_value=0.0, # Sẽ được KTV update sau
                deviation_percent=0.0,
                is_within_tolerance=True
            )
            
        messages.success(request, f"Đã lên lịch kiểm tra cho {relay.relay_code}")
        return redirect('check_detail', pk=check.pk)

    relays = Relay.objects.all()
    return render(request, 'checks/check_form.html', {'relays': relays})

@login_required
def check_detail(request, pk):
    """View chi tiết đợt kiểm tra và form nhập liệu."""
    check = get_object_or_404(PeriodicCheck, pk=pk)
    
    # Ghép Item với Setting tương ứng
    items_with_settings = []
    for item in check.items.all():
        setting = RelaySetting.objects.filter(relay=check.relay, parameter_code=item.parameter_code).first()
        items_with_settings.append({
            'item': item,
            'setting': setting
        })
        
    context = {
        'check': check,
        'items': items_with_settings
    }
    return render(request, 'checks/check_detail.html', context)

@login_required
def check_update_item(request, pk):
    """View API dùng cho HTMX để lưu và tính toán sai lệch realtime."""
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        measured_value = float(request.POST.get('measured_value', 0))
        
        item = get_object_or_404(PeriodicCheckItem, pk=item_id)
        setting = RelaySetting.objects.filter(relay=item.periodic_check.relay, parameter_code=item.parameter_code).first()
        
        if setting:
            std = setting.standard_value
            # Calculate deviation %
            if std != 0:
                deviation = abs(measured_value - std) / abs(std) * 100
            else:
                deviation = 0.0
                
            is_within = setting.tolerance_min <= measured_value <= setting.tolerance_max
            
            item.measured_value = measured_value
            item.deviation_percent = deviation
            item.is_within_tolerance = is_within
            item.save()
            
            return render(request, 'checks/partials/_item_row.html', {
                'item_dict': {'item': item, 'setting': setting}
            })
            
    return JsonResponse({'success': False}, status=400)

@login_required
def check_complete(request, pk):
    """Đóng đợt kiểm tra."""
    if request.method == 'POST':
        check = get_object_or_404(PeriodicCheck, pk=pk)
        check.check_status = 'COMPLETED'
        check.actual_check_date = datetime.now()
        check.save()
        messages.success(request, "Đã lưu hoàn thành đợt kiểm tra.")
    return redirect('check_detail', pk=pk)
