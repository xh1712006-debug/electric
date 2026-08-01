import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.cache import cache
from django.contrib import messages

@login_required
def bulk_create_ui(request):
    """Render the UI for Bulk Sheet Creation (Test Utility)"""
    # Only allow Dispatcher for testing
    if not request.user.is_superuser and not request.user.has_perm('sheets.can_create_sheet'):
        messages.error(request, "Bạn không có quyền truy cập tính năng Test này.")
        return redirect('sheet_list')
    from django.utils import timezone
    from datetime import timedelta
    from sheets.models import SettingSheet

    # Get sheets created by this user in the last 24 hours
    time_threshold = timezone.now() - timedelta(hours=24)
    recent_sheets_qs = SettingSheet.objects.filter(
        created_by=request.user,
        created_at__gte=time_threshold
    ).order_by('-created_at')
    
    total_recent = recent_sheets_qs.count()
    from django.core.paginator import Paginator
    paginator = Paginator(recent_sheets_qs, 20)
    page_number = request.GET.get('page', 1)
    recent_sheets = paginator.get_page(page_number)

    return render(request, 'sheets/bulk_create.html', {
        'recent_sheets': recent_sheets,
        'total_recent': total_recent
    })

@login_required
def bulk_create_execute(request):
    """API endpoint to execute bulk creation logic via Celery with Idempotency"""
    if not request.user.is_superuser and not request.user.has_perm('sheets.can_create_sheet'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    idempotency_key = request.POST.get('idempotency_key')
    if not idempotency_key:
        return JsonResponse({'error': 'Mã Idempotency (idempotency_key) là bắt buộc'}, status=400)
        
    scan_files = request.FILES.getlist('scan_files')
    if not scan_files:
        return JsonResponse({'error': 'Vui lòng tải lên ít nhất 1 file.'}, status=400)
        
    # Kiểm tra Idempotency Lock
    cached_status = cache.get(idempotency_key)
    if cached_status:
        if cached_status == 'PROCESSING':
            return JsonResponse({'status': 'PROCESSING', 'message': 'Hệ thống đang xử lý yêu cầu này, vui lòng đợi.'})
        else:
            return JsonResponse({'status': 'COMPLETED', 'data': cached_status})
            
    # Khóa Idempotency
    cache.set(idempotency_key, 'PROCESSING', timeout=86400)
    
    # Chuẩn bị dữ liệu: Tạo các bản ghi SettingSheet với trạng thái DRAFT
    from stations.models import Station, Relay
    from sheets.models import SettingSheet
    import random
    import uuid

    station_ids = list(Station.objects.values_list('id', flat=True))
    relay_ids = list(Relay.objects.values_list('id', flat=True))
    
    sheet_ids = []
    
    for f in scan_files:
        station_id = random.choice(station_ids) if station_ids else None
        relay_id = random.choice(relay_ids) if relay_ids else None
        # Generate random sheet code
        unique_id = str(uuid.uuid4())[:8].upper()
        sheet_code = f"AUTO-{unique_id}"
        
        sheet = SettingSheet.objects.create(
            sheet_code=sheet_code,
            title=f.name,
            relay_id=relay_id,
            station_id=station_id,
            scan_file=f,
            status='DRAFT', # Will be processed by Celery
            created_by=request.user
        )
        sheet_ids.append(sheet.id)
    
    # Kích hoạt Celery Worker
    from sheets.tasks import execute_bulk_create_task
    execute_bulk_create_task.delay(idempotency_key, request.user.id, sheet_ids)
    
    return JsonResponse({
        'status': 'ACCEPTED',
        'message': f'Đã đưa {len(sheet_ids)} file vào hàng đợi Celery (Background Processing). Vui lòng chờ thông báo (Toast) khi hoàn tất.'
    })

@login_required
def api_extract_test_ui(request):
    """Render the UI for API Extract Test"""
    if not request.user.is_superuser and not request.user.has_perm('sheets.can_create_sheet'):
        messages.error(request, "Bạn không có quyền truy cập tính năng Test này.")
        return redirect('sheet_list')
    return render(request, 'sheets/api_extract_test.html')

@login_required
def api_extract_test_execute(request):
    """Mock API endpoint to simulate data extraction"""
    if not request.user.is_superuser and not request.user.has_perm('sheets.can_create_sheet'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    scan_files = request.FILES.getlist('scan_files')
    if not scan_files:
        return JsonResponse({'error': 'Vui lòng tải lên ít nhất 1 file.'}, status=400)
        
    api_url = request.POST.get('api_url')
    
    if api_url:
        import requests
        # Pass files to the real API
        try:
            # Prepare files for requests
            files_to_send = []
            for f in scan_files:
                # requests expects a tuple (filename, fileobj, content_type)
                files_to_send.append(('scan_files', (f.name, f.read(), f.content_type)))
                
            response = requests.post(api_url, files=files_to_send, timeout=30)
            # Try to return the JSON directly from the API
            try:
                api_json = response.json()
                return JsonResponse({
                    'status': 'SUCCESS' if response.ok else 'ERROR',
                    'message': f'Phản hồi từ {api_url}',
                    'data': api_json,
                    'http_status': response.status_code
                })
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'error': 'API không trả về định dạng JSON hợp lệ.',
                    'raw_response': response.text[:500] # Return partial raw response for debugging
                })
        except requests.exceptions.RequestException as e:
            return JsonResponse({
                'status': 'ERROR',
                'error': f'Lỗi khi kết nối đến API: {str(e)}'
            })
        
    # Simulate processing and return mock data if no api_url provided
    # For multiple files, we'll return an array of results
    import time
    time.sleep(1) # Simulate API delay
    
    results = []
    for f in scan_files:
        results.append({
            'file_name': f.name,
            'status': 'success',
            'extracted_data': {
                'Tên Trạm': 'Trạm Mock 110kV',
                'Ngăn lộ': 'Lộ 171',
                'Loại Rơ-le': 'SEL-311C',
                'Hãng sản xuất': 'Schweitzer Engineering Laboratories',
                'Các thông số': {
                    'I>>': '10A',
                    't>>': '0.1s',
                    'I>': '5A',
                    't>': '0.5s'
                }
            }
        })
        
    return JsonResponse({
        'status': 'SUCCESS',
        'message': f'Đã trích xuất thành công {len(scan_files)} file.',
        'data': results
    })
