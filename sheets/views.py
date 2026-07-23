from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
import random
import time
from .models import SettingSheet, SignatureRecord
from stations.models import Relay
from .services import evn_service

import hashlib
from django.core.cache import cache

@login_required
def sheet_list(request):
    """View danh sách phiếu chỉnh định."""
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    page_number = request.GET.get('page', 1)
    
    cache_version = cache.get('sheet_list_version', 1)
    key_string = f"sheet_list_v{cache_version}_user_{request.user.id}_q_{search_query}_s_{status_filter}_p_{page_number}"
    cache_key = hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    cached_context = cache.get(cache_key)
    if cached_context:
        return render(request, 'sheets/sheet_list.html', cached_context)
        
    sheets = SettingSheet.objects.select_related('created_by', 'relay', 'relay__bay', 'relay__bay__station', 'station').all().order_by('-created_at')
    
    # Filter for DISPATCHER (chỉ xem phiếu mình tạo)
    if request.user.groups.filter(name='DISPATCHER').exists() and not request.user.is_superuser:
        sheets = sheets.filter(created_by=request.user)
    
    # Filter for STATION_LEADER
    if request.user.groups.filter(name='STATION_LEADER').exists() and not request.user.is_superuser:
        try:
            station = request.user.userprofile.station
            if station:
                from django.db.models import Q
                sheets = sheets.filter(Q(station=station) | Q(relay__bay__station=station)).distinct()
            else:
                sheets = sheets.none()
        except Exception:
            pass

    from django.core.paginator import Paginator

    if search_query:
        sheets = sheets.filter(sheet_code__icontains=search_query)
        
    if status_filter:
        sheets = sheets.filter(status__in=status_filter.split(','))

    paginator = Paginator(sheets, 40)
    page_obj = paginator.get_page(page_number)
    
    # Force queryset evaluation before caching
    _ = list(page_obj.object_list)

    list_title = 'Tất cả Phiếu Chỉnh định'
    if status_filter == 'COMPLETED':
        list_title = 'Hồ sơ Đã Ban hành'
    elif status_filter == 'PENDING_ADMIN_APPROVAL':
        list_title = 'Phiếu Chờ Ký Duyệt'

    context = {
        'sheets': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'list_title': list_title
    }
    
    cache.set(cache_key, context, timeout=86400)
    
    return render(request, 'sheets/sheet_list.html', context)

@login_required
def my_sheets(request):
    """View danh sách phiếu của tôi."""
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    page_number = request.GET.get('page', 1)
    
    cache_version = cache.get('sheet_list_version', 1)
    key_string = f"my_sheets_v{cache_version}_user_{request.user.id}_q_{search_query}_s_{status_filter}_p_{page_number}"
    cache_key = hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    cached_context = cache.get(cache_key)
    if cached_context:
        return render(request, 'sheets/sheet_list.html', cached_context)

    # Lấy các phiếu do mình tạo hoặc được assign cho mình
    from django.db.models import Q
    sheets = SettingSheet.objects.select_related('created_by', 'relay', 'relay__bay', 'relay__bay__station', 'station').filter(
        Q(created_by=request.user) | Q(assigned_to=request.user) | Q(supervisor_assigned=request.user)
    ).order_by('-created_at')
    
    from django.core.paginator import Paginator

    if search_query:
        sheets = sheets.filter(sheet_code__icontains=search_query)
        
    if status_filter:
        sheets = sheets.filter(status__in=status_filter.split(','))

    paginator = Paginator(sheets, 40)
    page_obj = paginator.get_page(page_number)
    
    _ = list(page_obj.object_list)

    context = {
        'sheets': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'list_title': 'Phiếu của tôi'
    }
    
    cache.set(cache_key, context, timeout=86400)
    
    return render(request, 'sheets/sheet_list.html', context)

@login_required
def updated_sheets(request):
    """View danh sách các phiếu có thay đổi thông số so với bản cũ."""
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    page_number = request.GET.get('page', 1)
    
    cache_version = cache.get('sheet_list_version', 1)
    key_string = f"updated_sheets_v{cache_version}_user_{request.user.id}_q_{search_query}_s_{status_filter}_p_{page_number}"
    cache_key = hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    cached_context = cache.get(cache_key)
    if cached_context:
        return render(request, 'sheets/sheet_list.html', cached_context)

    sheets = SettingSheet.objects.select_related('created_by', 'relay', 'relay__bay', 'relay__bay__station', 'station').filter(has_parameters_changed=True).order_by('-created_at')

    from django.core.paginator import Paginator
    
    if search_query:
        sheets = sheets.filter(sheet_code__icontains=search_query)
        
    if status_filter:
        sheets = sheets.filter(status__in=status_filter.split(','))

    paginator = Paginator(sheets, 40)
    page_obj = paginator.get_page(page_number)
    
    _ = list(page_obj.object_list)

    context = {
        'sheets': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'list_title': 'Phiếu Có Thay Đổi Thông Số (Cần Lưu Ý)'
    }
    
    cache.set(cache_key, context, timeout=86400)
    
    return render(request, 'sheets/sheet_list.html', context)

@login_required
def sheet_create(request):
    """View upload PDF và tạo phiếu."""
    if request.method == 'POST':
        sheet_code = request.POST.get('sheet_code')
        title = request.POST.get('title', '')
        relay_text = request.POST.get('relay_text')
        station_id = request.POST.get('station_id')
        scan_file = request.FILES.get('scan_file')
        
        if not all([sheet_code, relay_text, station_id, scan_file]):
            messages.error(request, "Vui lòng điền đủ Mã Phiếu, Trạm đích, Rơ-le áp dụng và Tải file scan.")
            return redirect('sheet_create')
            
        if SettingSheet.objects.filter(sheet_code=sheet_code).exists():
            messages.error(request, f"Mã phiếu '{sheet_code}' đã tồn tại trong hệ thống. Vui lòng chọn mã khác.")
            return redirect('sheet_create')
            
        relay = Relay.objects.filter(relay_code=relay_text).first()
        from stations.models import Station
        station = Station.objects.filter(id=station_id).first()
        
        sheet = SettingSheet.objects.create(
            sheet_code=sheet_code,
            title=title,
            relay=relay,
            relay_text=relay_text if not relay else None,
            station=station,
            scan_file=scan_file,
            status='ISSUED', # Directly issued after OCR
            created_by=request.user
        )
        
        # Auto-trigger OCR
        perform_mock_ocr(sheet)
        
        messages.success(request, f"Đã tạo phiếu {sheet.sheet_code} và quét OCR thành công!")
        return redirect('sheet_detail', pk=sheet.pk)

    from stations.models import Station
    stations = Station.objects.all()
    relays = Relay.objects.all()
    initial_relay = request.GET.get('relay_code', '')
    return render(request, 'sheets/sheet_form.html', {
        'stations': stations,
        'relays': relays,
        'initial_relay': initial_relay
    })

@login_required
def sheet_detail(request, pk):
    """View chi tiết phiếu - Split View."""
    sheet = get_object_or_404(SettingSheet, pk=pk)
    
    # Get parameters for the selected relay
    settings = sheet.relay.settings.all() if sheet.relay else []
    
    # Lấy danh sách user theo Role để dùng cho Popup Giao việc
    from django.contrib.auth.models import User
    dispatchers = User.objects.filter(groups__name='DISPATCHER')
    reviewers = User.objects.filter(groups__name='ADMIN')
    
    if request.user.groups.filter(name='STATION_LEADER').exists() and not request.user.is_superuser:
        try:
            station = request.user.userprofile.station
            technicians = User.objects.filter(groups__name='TECHNICIAN', userprofile__station=station)
            supervisors = User.objects.filter(groups__name='SUPERVISOR', userprofile__station=station)
        except Exception:
            technicians = User.objects.none()
            supervisors = User.objects.none()
    else:
        technicians = User.objects.filter(groups__name='TECHNICIAN')
        supervisors = User.objects.filter(groups__name='SUPERVISOR')
    
    dispatcher_sig = sheet.signatures.filter(role='DISPATCHER').first()
    tech_sig = sheet.signatures.filter(role='TECHNICIAN').first()
    sup_sig = sheet.signatures.filter(role='SUPERVISOR').first()
    admin_sig = sheet.signatures.filter(role='ADMIN').first()
    
    # Logic: So sánh với phiếu cũ gần nhất
    previous_sheet = None
    differences = []
    has_previous = False
    
    display_data = sheet.extracted_data

    if sheet.relay and display_data:
        previous_sheet = SettingSheet.objects.filter(
            relay=sheet.relay,
            created_at__lt=sheet.created_at
        ).order_by('-created_at').first()
        
        if previous_sheet:
            has_previous = True
            old_data = previous_sheet.extracted_data or []
            new_data = display_data or []
            
            # Convert to dict for easier comparison by parameter_code
            old_dict = {item.get('parameter_code'): item for item in old_data if item.get('parameter_code')}
            new_dict = {item.get('parameter_code'): item for item in new_data if item.get('parameter_code')}
            
            # Compare
            # 1. Added and Changed
            for code, new_item in new_dict.items():
                if code not in old_dict:
                    differences.append({
                        'code': code,
                        'name': new_item.get('parameter_name', ''),
                        'unit': new_item.get('unit', ''),
                        'type': 'ADDED',
                        'old_value': None,
                        'new_value': new_item.get('value')
                    })
                else:
                    old_item = old_dict[code]
                    try:
                        old_val = float(old_item.get('value', 0))
                        new_val = float(new_item.get('value', 0))
                        if old_val != new_val:
                            differences.append({
                                'code': code,
                                'name': new_item.get('parameter_name', ''),
                                'unit': new_item.get('unit', ''),
                                'type': 'CHANGED',
                                'old_value': old_val,
                                'new_value': new_val
                            })
                    except (ValueError, TypeError):
                        # In case values are not convertible to float
                        if str(old_item.get('value')) != str(new_item.get('value')):
                            differences.append({
                                'code': code,
                                'name': new_item.get('parameter_name', ''),
                                'unit': new_item.get('unit', ''),
                                'type': 'CHANGED',
                                'old_value': old_item.get('value'),
                                'new_value': new_item.get('value')
                            })
            
            # 2. Removed
            for code, old_item in old_dict.items():
                if code not in new_dict:
                    differences.append({
                        'code': code,
                        'name': old_item.get('parameter_name', ''),
                        'unit': old_item.get('unit', ''),
                        'type': 'REMOVED',
                        'old_value': old_item.get('value'),
                        'new_value': None
                    })
    
    # Calculate counts
    added_count = sum(1 for d in differences if d['type'] == 'ADDED')
    removed_count = sum(1 for d in differences if d['type'] == 'REMOVED')
    changed_count = sum(1 for d in differences if d['type'] == 'CHANGED')
    total_diff_count = len(differences)
    
    
    # Build history logs
    history_logs = []
    
    # 1. Created
    history_logs.append({
        'time': sheet.created_at,
        'action': 'Khởi tạo phiếu (Tải lên bản scan OCR)',
        'user_name': sheet.created_by.get_full_name() or sheet.created_by.username if sheet.created_by else 'Hệ thống',
        'icon': 'fa-file-upload',
        'color_class': 'text-blue-500',
        'bg_class': 'bg-blue-100',
        'border_class': 'border-blue-200'
    })
    
    # 2. Signatures
    for sig in sheet.signatures.all().order_by('signed_at'):
        if sig.role == 'DISPATCHER':
            history_logs.append({
                'time': sig.signed_at,
                'action': 'Duyệt lệnh và Chuyển về Trạm',
                'user_name': sig.signer_name,
                'icon': 'fa-paper-plane',
                'color_class': 'text-teal-500',
                'bg_class': 'bg-teal-100',
                'border_class': 'border-teal-200'
            })
        elif sig.role == 'TECHNICIAN':
            history_logs.append({
                'time': sig.signed_at,
                'action': 'KTV thi công cài đặt và Ký xác nhận',
                'user_name': sig.signer_name,
                'icon': 'fa-wrench',
                'color_class': 'text-green-500',
                'bg_class': 'bg-green-100',
                'border_class': 'border-green-200'
            })
        elif sig.role == 'SUPERVISOR':
            history_logs.append({
                'time': sig.signed_at,
                'action': 'Giám sát trạm kiểm tra và Ký xác nhận',
                'user_name': sig.signer_name,
                'icon': 'fa-eye',
                'color_class': 'text-emerald-500',
                'bg_class': 'bg-emerald-100',
                'border_class': 'border-emerald-200'
            })
        elif sig.role == 'ADMIN':
            history_logs.append({
                'time': sig.signed_at,
                'action': 'Quản trị viên phê duyệt ban hành',
                'user_name': sig.signer_name,
                'icon': 'fa-check-double',
                'color_class': 'text-amber-500',
                'bg_class': 'bg-amber-100',
                'border_class': 'border-amber-200'
            })
            
    if getattr(sheet, 'assigned_at', None) or sheet.assigned_to or sheet.supervisor_assigned:
        history_logs.append({
            'time': sheet.assigned_at or getattr(dispatcher_sig, 'signed_at', sheet.created_at),
            'action': 'Trưởng trạm phân công KTV & Giám sát',
            'user_name': 'Trưởng nhóm Trạm',
            'icon': 'fa-user-tag',
            'color_class': 'text-purple-500',
            'bg_class': 'bg-purple-100',
            'border_class': 'border-purple-200'
        })

    # 3. Edit logs
    if isinstance(sheet.edit_logs, list):
        from django.utils.dateparse import parse_datetime
        for log in sheet.edit_logs:
            try:
                dt = parse_datetime(log.get('time', ''))
                if dt:
                    changes_text = "<br>".join([f"• {c}" for c in log.get('changes', [])])
                    history_logs.append({
                        'time': dt,
                        'action': f"Sửa đổi thông số OCR:<br><span class='text-xs text-slate-500 font-medium'>{changes_text}</span>",
                        'user_name': log.get('user', 'Người Điều phối'),
                        'icon': 'fa-edit',
                        'color_class': 'text-orange-500',
                        'bg_class': 'bg-orange-100',
                        'border_class': 'border-orange-200'
                    })
            except Exception:
                pass

    # Sort descending
    history_logs.sort(key=lambda x: x['time'], reverse=True)
    
    context = {
        'sheet': sheet,
        'settings': settings,
        'reviewers': reviewers,
        'dispatchers': dispatchers,
        'technicians': technicians,
        'supervisors': supervisors,
        'dispatcher_sig': dispatcher_sig,
        'tech_sig': tech_sig,
        'sup_sig': sup_sig,
        'admin_sig': admin_sig,
        'previous_sheet': previous_sheet,
        'differences': differences,
        'has_previous': has_previous,
        'added_count': added_count,
        'removed_count': removed_count,
        'changed_count': changed_count,
        'total_diff_count': total_diff_count,
        'display_data': display_data,
        'history_logs': history_logs,
    }
    
    return render(request, 'sheets/sheet_detail.html', context)

@login_required
def sheet_assign(request, pk):
    """View để Dispatcher phân công phiếu cho KTV và Giám sát."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        assignee_id = request.POST.get('assignee_id')
        supervisor_id = request.POST.get('supervisor_id')
        new_status = request.POST.get('status')
        
        from django.contrib.auth.models import User
        if assignee_id:
            sheet.assigned_to = User.objects.get(pk=assignee_id)
        if supervisor_id:
            sheet.supervisor_assigned = User.objects.get(pk=supervisor_id)
        
        if assignee_id or supervisor_id:
            from django.utils import timezone
            sheet.assigned_at = timezone.now()
            
        valid_statuses = [s[0] for s in SettingSheet.STATUS_CHOICES]
        if new_status in valid_statuses:
            sheet.status = new_status
            
        sheet.save()
        
        # --- Send real-time notifications via Channels ---
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                if assignee_id:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{assignee_id}",
                        {
                            "type": "send_notification",
                            "title": "Nhiệm vụ Mới",
                            "message": f"Điều phối viên vừa phân công Phiếu {sheet.sheet_code} cho bạn."
                        }
                    )
                if supervisor_id:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{supervisor_id}",
                        {
                            "type": "send_notification",
                            "title": "Nhiệm vụ Giám sát",
                            "message": f"Bạn được chỉ định giám sát Phiếu {sheet.sheet_code}."
                        }
                    )
        except Exception as e:
            print("Channels error:", e)
            
        messages.success(request, f"Đã phân công phiếu {sheet.sheet_code} thành công!")
        return redirect('sheet_detail', pk=pk)
    return redirect('sheet_list')

@login_required
def sheet_route_to_station(request, pk):
    """
    Route a sheet directly to the station.
    Allowed for DISPATCHER, ADMIN, or the creator of the sheet.
    """
    sheet = get_object_or_404(SettingSheet, pk=pk)
    
    if request.method == 'POST':
        # Check permissions: Dispatcher
        has_perm = request.user.groups.filter(name='DISPATCHER').exists()
        
        if has_perm and sheet.status == 'ISSUED':
            if sheet.created_by != request.user and not request.user.is_superuser:
                messages.error(request, "Bạn chỉ có thể duyệt chuyển trạm đối với những phiếu do chính bạn khởi tạo.")
                return redirect('sheet_detail', pk=pk)
                
            sheet.status = 'ROUTED_TO_STATION'
            sheet.save()
            
            # Ghi nhận người duyệt
            import hashlib
            from django.utils.timezone import now
            hash_input = f"{sheet.id}-{request.user.username}-{now()}".encode('utf-8')
            sig_hash = hashlib.sha256(hash_input).hexdigest()
            
            SignatureRecord.objects.create(
                sheet=sheet,
                signer_name=request.user.get_full_name() or request.user.username,
                role='DISPATCHER',
                signature_hash=sig_hash
            )
            
            messages.success(request, f"Đã duyệt và chuyển phiếu {sheet.sheet_code} về Trạm thành công!")
        else:
            messages.error(request, "Bạn không có quyền hoặc phiếu không ở trạng thái hợp lệ.")
        return redirect('sheet_detail', pk=pk)
    return redirect('sheet_list')

@login_required
def sheet_update_status(request, pk):
    """View update status via HTMX (mock logic)."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        new_status = request.POST.get('status')
        
        valid_statuses = [s[0] for s in SettingSheet.STATUS_CHOICES]
        if new_status in valid_statuses:
            sheet.status = new_status
            sheet.save()
            
        return render(request, 'sheets/partials/_status_badge.html', {'sheet': sheet})
    return redirect('sheet_list')

@login_required
def initiate_signature(request, pk):
    """View giả lập tạo phiên ký số EVN."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        role = request.POST.get('role', 'ADMIN')
        
        # Gọi Mock Service
        res = evn_service.initiate_signing_session(sheet.id, role)
        
        return JsonResponse({
            'success': True,
            'session_id': res['session_id'],
            'signing_url': res['signing_url'],
            'role': role
        })
    return JsonResponse({'success': False}, status=400)

@login_required
def confirm_signature(request, pk):
    """View giả lập xác nhận ký số thành công."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        role = request.POST.get('role')
        signer_name = request.user.get_full_name() or request.user.username
        
        # Gọi Mock Service để xác thực và lấy chữ ký
        res = evn_service.confirm_signature(sheet, signer_name, role)
        
        if res['success']:
            tech_sig_exists = sheet.signatures.filter(role='TECHNICIAN').exists()
            sup_sig_exists = sheet.signatures.filter(role='SUPERVISOR').exists()

            # Server-side validation of signature sequence
            if role == 'SUPERVISOR' and not tech_sig_exists:
                return JsonResponse({'success': False, 'error': 'Technician must sign first'}, status=400)
            if role == 'ADMIN' and not sup_sig_exists:
                return JsonResponse({'success': False, 'error': 'Supervisor must sign first'}, status=400)

            # Lưu chữ ký vào DB
            SignatureRecord.objects.create(
                sheet=sheet,
                signer_name=signer_name,
                role=role,
                signature_hash=res['signature_hash']
            )
            
            # Cập nhật trạng thái phiếu dựa trên Role
            if role == 'TECHNICIAN' and sheet.status == 'RECEIVED':
                pass # Chờ thêm Giám sát trạm
            elif role == 'SUPERVISOR' and sheet.status == 'RECEIVED':
                sheet.status = 'PENDING_ADMIN_APPROVAL' # Đẩy lên cho ADMIN duyệt
                sheet.save()
            elif role == 'ADMIN' and sheet.status == 'PENDING_ADMIN_APPROVAL':
                sheet.status = 'COMPLETED'
                sheet.save()
                
            tech_sig = sheet.signatures.filter(role='TECHNICIAN').first()
            sup_sig = sheet.signatures.filter(role='SUPERVISOR').first()
            admin_sig = sheet.signatures.filter(role='ADMIN').first()
                
            return render(request, 'sheets/partials/_signature_panel.html', {
                'sheet': sheet,
                'tech_sig': tech_sig,
                'sup_sig': sup_sig,
                'admin_sig': admin_sig
            })
            
    return JsonResponse({'success': False}, status=400)

def perform_mock_ocr(sheet):
    """Hàm chạy AI OCR (mock) trực tiếp."""
    import random
    extracted_data = []
    
    # 1. Trích xuất metadata từ PDF (Tên trạm, Mã rơ-le)
    station_name = sheet.station.station_name if sheet.station else 'Không xác định'
    relay_code = sheet.relay.relay_code if sheet.relay else (sheet.relay_text or 'Không xác định')
    
    extracted_data.append({
        'parameter_code': 'STATION_NAME',
        'parameter_name': 'Tên Trạm (Nhận diện)',
        'unit': '',
        'value': station_name,
        'original_value': station_name,
        'confidence': round(random.uniform(95.0, 99.9), 1)
    })
    
    extracted_data.append({
        'parameter_code': 'RELAY_CODE',
        'parameter_name': 'Mã Rơ-le (Nhận diện)',
        'unit': '',
        'value': relay_code,
        'original_value': relay_code,
        'confidence': round(random.uniform(95.0, 99.9), 1)
    })
    
    # 2. Trích xuất thông số
    if sheet.relay and sheet.relay.settings.exists():
        for setting in sheet.relay.settings.all():
            is_perfect = random.random() > 0.1
            val = setting.standard_value if is_perfect else setting.standard_value * random.uniform(0.95, 1.05)
            val = round(val, 2)
            
            conf = random.uniform(85.0, 99.9) if not is_perfect else random.uniform(97.0, 99.9)
            
            extracted_data.append({
                'parameter_code': setting.parameter_code,
                'parameter_name': setting.parameter_name,
                'unit': setting.unit,
                'value': val,
                'original_value': val,
                'confidence': round(conf, 1)
            })
    else:
        # Nếu không có relay hoặc relay chưa cấu hình thông số, tạo random 20-30 thông số
        mock_params_template = [
            {'code': 'I_max', 'name': 'Dòng điện cắt cực đại', 'unit': 'A', 'min': 10, 'max': 50},
            {'code': 'T_delay', 'name': 'Thời gian trễ cắt', 'unit': 's', 'min': 0.1, 'max': 2.0},
            {'code': 'V_min', 'name': 'Điện áp cắt thấp áp', 'unit': 'V', 'min': 90, 'max': 110},
            {'code': 'V_max', 'name': 'Điện áp cắt quá áp', 'unit': 'V', 'min': 120, 'max': 150},
            {'code': 'F_min', 'name': 'Tần số cắt thấp', 'unit': 'Hz', 'min': 48, 'max': 49.5},
            {'code': 'F_max', 'name': 'Tần số cắt cao', 'unit': 'Hz', 'min': 50.5, 'max': 52},
            {'code': 'Z_reach_1', 'name': 'Vùng bảo vệ khoảng cách 1', 'unit': 'Ohm', 'min': 1, 'max': 10},
            {'code': 'Z_reach_2', 'name': 'Vùng bảo vệ khoảng cách 2', 'unit': 'Ohm', 'min': 10, 'max': 25},
            {'code': 'Z_reach_3', 'name': 'Vùng bảo vệ khoảng cách 3', 'unit': 'Ohm', 'min': 25, 'max': 50},
            {'code': 'I_diff', 'name': 'Dòng điện so lệch', 'unit': 'A', 'min': 0.5, 'max': 5.0},
            {'code': 'T_diff', 'name': 'Thời gian cắt so lệch', 'unit': 's', 'min': 0.0, 'max': 0.5},
            {'code': 'Dir_angle', 'name': 'Góc hướng dòng', 'unit': 'Deg', 'min': -90, 'max': 90},
            {'code': 'I_earth_1', 'name': 'Dòng chạm đất cực đại cấp 1', 'unit': 'A', 'min': 1, 'max': 10},
            {'code': 'T_earth_1', 'name': 'Thời gian trễ chạm đất cấp 1', 'unit': 's', 'min': 0.1, 'max': 1.0},
            {'code': 'I_earth_2', 'name': 'Dòng chạm đất cực đại cấp 2', 'unit': 'A', 'min': 10, 'max': 50},
            {'code': 'P_reverse', 'name': 'Công suất ngược', 'unit': 'kW', 'min': 5, 'max': 20},
            {'code': 'T_reverse', 'name': 'Thời gian cắt công suất ngược', 'unit': 's', 'min': 0.5, 'max': 5.0},
            {'code': 'I_thermal', 'name': 'Dòng bảo vệ quá nhiệt', 'unit': 'A', 'min': 50, 'max': 200},
            {'code': 'K_thermal', 'name': 'Hệ số thời gian nhiệt', 'unit': '', 'min': 0.1, 'max': 1.5},
            {'code': 'T_reclose_1', 'name': 'Thời gian tự đóng lại lần 1', 'unit': 's', 'min': 0.5, 'max': 3.0},
            {'code': 'T_reclose_2', 'name': 'Thời gian tự đóng lại lần 2', 'unit': 's', 'min': 10, 'max': 30},
            {'code': 'N_reclose', 'name': 'Số lần tự đóng lại', 'unit': 'lần', 'min': 1, 'max': 3},
            {'code': 'U_sync', 'name': 'Điện áp hòa đồng bộ', 'unit': 'V', 'min': 95, 'max': 105},
            {'code': 'F_sync', 'name': 'Độ lệch tần số hòa đồng bộ', 'unit': 'Hz', 'min': 0.05, 'max': 0.2},
            {'code': 'Phi_sync', 'name': 'Góc lệch pha hòa đồng', 'unit': 'Deg', 'min': 5, 'max': 15},
            {'code': 'I_unbalance', 'name': 'Dòng không cân bằng', 'unit': 'A', 'min': 1, 'max': 5},
            {'code': 'V_unbalance', 'name': 'Điện áp không cân bằng', 'unit': 'V', 'min': 2, 'max': 10},
            {'code': 'T_start', 'name': 'Thời gian khởi động', 'unit': 's', 'min': 1, 'max': 10}
        ]
        
        # Tự động sinh thêm thông số cho các pha A, B, C, N để làm phong phú dữ liệu (đủ 50-60 dòng)
        expanded_params = []
        for p in mock_params_template:
            expanded_params.append(p)
            if 'chạm đất' not in p['name'] and p['unit'] in ['A', 'V']:
                expanded_params.append({**p, 'code': f"{p['code']}_phA", 'name': f"{p['name']} (Pha A)"})
                expanded_params.append({**p, 'code': f"{p['code']}_phB", 'name': f"{p['name']} (Pha B)"})
                expanded_params.append({**p, 'code': f"{p['code']}_phC", 'name': f"{p['name']} (Pha C)"})
            if 'chạm đất' in p['name'] or 'không cân bằng' in p['name']:
                expanded_params.append({**p, 'code': f"{p['code']}_N", 'name': f"{p['name']} (Trung tính)"})

        # Chọn 50 thông số đầu tiên (hoặc ngẫu nhiên 50)
        selected_params = random.sample(expanded_params, min(50, len(expanded_params)))
        
        for p in selected_params:
            val = round(random.uniform(p['min'], p['max']), 2)
            conf = random.uniform(85.0, 99.9)
            extracted_data.append({
                'parameter_code': p['code'],
                'parameter_name': p['name'],
                'unit': p['unit'],
                'value': val,
                'original_value': val,
                'confidence': round(conf, 1)
            })
    
    sheet.extracted_data = extracted_data
    sheet.save()
    
    from .utils import update_has_parameters_changed_for_sheet
    update_has_parameters_changed_for_sheet(sheet)
    
    return extracted_data

@login_required
def run_mock_ocr(request, pk):
    """View giả lập quá trình chạy AI OCR (Dành cho trigger thủ công nếu cần)."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        
        if sheet.status not in ['DRAFT', 'ISSUED']:
            messages.error(request, "Phiếu đã được duyệt và chuyển trạm. Không thể chạy lại AI OCR.")
            return redirect('sheet_detail', pk=pk)
            
        time.sleep(1.5)
        perform_mock_ocr(sheet)
        return redirect('sheet_detail', pk=pk)
    return redirect('sheet_list')

@login_required
def sheet_save_actual_data(request, pk):
    """View cho phép KTV lưu thông số thực tế và Điều phối sửa lỗi OCR."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        
        if sheet.status not in ['DRAFT', 'ISSUED']:
            messages.error(request, "Phiếu đã được duyệt và chuyển trạm. Không thể sửa đổi thông số OCR nữa.")
            return redirect('sheet_detail', pk=pk)
            
        is_dispatcher = request.user.groups.filter(name='DISPATCHER').exists()
        
        if is_dispatcher:
            if sheet.extracted_data:
                updated_data = []
                changes = []
                for index, item in enumerate(sheet.extracted_data):
                    ocr_val = request.POST.get(f'ocr_value_{index}')
                    if ocr_val is not None and ocr_val.strip() != '':
                        old_val_raw = item.get('value', '')
                        new_val_raw = ocr_val.strip()
                        
                        is_changed = False
                        try:
                            # Nếu cả 2 đều là số, so sánh theo dạng số
                            old_float = float(old_val_raw)
                            new_float = float(new_val_raw)
                            if old_float != new_float:
                                is_changed = True
                                new_val = new_float
                            else:
                                new_val = old_val_raw # Giữ nguyên type cũ
                        except (ValueError, TypeError):
                            # Nếu là chuỗi (hoặc 1 trong 2 là chuỗi)
                            if str(old_val_raw) != new_val_raw:
                                is_changed = True
                            new_val = new_val_raw
                            
                        if is_changed:
                            if 'original_value' not in item:
                                item['original_value'] = old_val_raw
                            changes.append(f"{item.get('parameter_code')}: {old_val_raw} ➡️ {new_val}")
                            item['value'] = new_val
                            
                    updated_data.append(item)
                
                if changes and is_dispatcher:
                    from django.utils import timezone
                    edit_log = {
                        'time': timezone.now().isoformat(),
                        'user': request.user.get_full_name() or request.user.username,
                        'changes': changes
                    }
                    if not isinstance(sheet.edit_logs, list):
                        sheet.edit_logs = []
                    sheet.edit_logs.append(edit_log)
                    
                sheet.extracted_data = updated_data
                sheet.save()
                
                from .utils import update_has_parameters_changed_for_sheet
                update_has_parameters_changed_for_sheet(sheet)
                
                if changes and is_dispatcher:
                    msg = "Đã cập nhật sửa lỗi OCR: " + " | ".join(changes)
                    messages.success(request, msg)
                    
                    try:
                        from asgiref.sync import async_to_sync
                        from channels.layers import get_channel_layer
                        channel_layer = get_channel_layer()
                        if channel_layer and sheet.created_by:
                            # Gửi thông báo cho người tạo phiếu và người dùng khác liên quan
                            async_to_sync(channel_layer.group_send)(
                                f"user_{sheet.created_by.id}",
                                {
                                    "type": "send_notification",
                                    "title": "Cập nhật dữ liệu OCR",
                                    "message": f"Điều phối viên đã sửa thông số thiết kế trên Phiếu {sheet.sheet_code}: " + " | ".join(changes)
                                }
                            )
                    except Exception as e:
                        print("WebSocket Error:", e)
                else:
                    messages.success(request, 'Đã lưu thông số thành công!')
            else:
                messages.error(request, 'Phiếu chưa có dữ liệu thiết kế để cập nhật.')
        else:
            messages.error(request, 'Bạn không có quyền cập nhật thông số cho phiếu này.')
            
        return redirect('sheet_detail', pk=pk)
    return redirect('sheet_list')
