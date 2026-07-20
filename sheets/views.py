from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
import random
import time
from .models import SettingSheet, SignatureRecord
from stations.models import Relay
from .services import evn_service

@login_required
def sheet_list(request):
    """View danh sách phiếu chỉnh định."""
    sheets = SettingSheet.objects.all().order_by('-created_at')
    
    # Simple search
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    
    from django.core.paginator import Paginator

    if search_query:
        sheets = sheets.filter(sheet_code__icontains=search_query)
        
    if status_filter:
        sheets = sheets.filter(status__in=status_filter.split(','))

    paginator = Paginator(sheets, 40)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    list_title = 'Tất cả Phiếu Chỉnh định'
    if status_filter == 'COMPLETED':
        list_title = 'Hồ sơ Đã Ban hành'
    elif status_filter == 'PENDING_REVIEW':
        list_title = 'Phiếu Chờ Ký Duyệt'

    context = {
        'sheets': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'list_title': list_title
    }
    return render(request, 'sheets/sheet_list.html', context)

@login_required
def my_sheets(request):
    """View danh sách phiếu của tôi."""
    # Lấy các phiếu do mình tạo hoặc được assign cho mình
    from django.db.models import Q
    sheets = SettingSheet.objects.filter(
        Q(created_by=request.user) | Q(assigned_to=request.user) | Q(supervisor_assigned=request.user)
    ).order_by('-created_at')
    
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    
    from django.core.paginator import Paginator

    if search_query:
        sheets = sheets.filter(sheet_code__icontains=search_query)
        
    if status_filter:
        sheets = sheets.filter(status__in=status_filter.split(','))

    paginator = Paginator(sheets, 40)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'sheets': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'list_title': 'Phiếu của tôi'
    }
    return render(request, 'sheets/sheet_list.html', context)

@login_required
def updated_sheets(request):
    """View danh sách các phiếu có thay đổi thông số so với bản cũ."""
    all_sheets = SettingSheet.objects.select_related('relay').all().order_by('-created_at')
    
    updated_sheets_list = []
    
    for sheet in all_sheets:
        if sheet.relay and sheet.extracted_data:
            previous_sheet = SettingSheet.objects.filter(
                relay=sheet.relay,
                created_at__lt=sheet.created_at
            ).order_by('-created_at').first()
            
            if previous_sheet:
                old_data = previous_sheet.extracted_data or []
                new_data = sheet.extracted_data or []
                
                old_dict = {item.get('parameter_code'): item for item in old_data if item.get('parameter_code')}
                new_dict = {item.get('parameter_code'): item for item in new_data if item.get('parameter_code')}
                
                has_diff = False
                for code, new_item in new_dict.items():
                    if code not in old_dict:
                        has_diff = True
                        break
                    else:
                        try:
                            old_val = float(old_dict[code].get('value', 0))
                            new_val = float(new_item.get('value', 0))
                            if old_val != new_val:
                                has_diff = True
                                break
                        except (ValueError, TypeError):
                            if str(old_dict[code].get('value')) != str(new_item.get('value')):
                                has_diff = True
                                break
                
                if not has_diff:
                    for code in old_dict:
                        if code not in new_dict:
                            has_diff = True
                            break
                            
                if has_diff:
                    updated_sheets_list.append(sheet)

    from django.core.paginator import Paginator
    paginator = Paginator(updated_sheets_list, 40)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'sheets': page_obj,
        'list_title': 'Phiếu Có Thay Đổi Thông Số (Cần Lưu Ý)'
    }
    return render(request, 'sheets/sheet_list.html', context)

@login_required
def sheet_create(request):
    """View upload PDF và tạo phiếu."""
    if request.method == 'POST':
        sheet_code = request.POST.get('sheet_code')
        title = request.POST.get('title', '')
        relay_text = request.POST.get('relay_text')
        scan_file = request.FILES.get('scan_file')
        
        if not all([sheet_code, relay_text, scan_file]):
            messages.error(request, "Vui lòng điền đủ Mã Phiếu, Rơ-le áp dụng và Tải file scan.")
            return redirect('sheet_create')
            
        if SettingSheet.objects.filter(sheet_code=sheet_code).exists():
            messages.error(request, f"Mã phiếu '{sheet_code}' đã tồn tại trong hệ thống. Vui lòng chọn mã khác.")
            return redirect('sheet_create')
            
        relay = Relay.objects.filter(relay_code=relay_text).first()
        
        sheet = SettingSheet.objects.create(
            sheet_code=sheet_code,
            title=title,
            relay=relay,
            relay_text=relay_text if not relay else None,
            scan_file=scan_file,
            status='ISSUED', # Directly issued after OCR
            created_by=request.user
        )
        
        # Auto-trigger OCR
        perform_mock_ocr(sheet)
        
        messages.success(request, f"Đã tạo phiếu {sheet.sheet_code} và quét OCR thành công!")
        return redirect('sheet_detail', pk=sheet.pk)

    relays = Relay.objects.all()
    initial_relay = request.GET.get('relay_code', '')
    return render(request, 'sheets/sheet_form.html', {
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
    reviewers = User.objects.filter(groups__name='REVIEWER')
    dispatchers = User.objects.filter(groups__name='DISPATCHER')
    technicians = User.objects.filter(groups__name='TECHNICIAN')
    supervisors = User.objects.filter(groups__name='SUPERVISOR')
    
    tech_sig = sheet.signatures.filter(role='TECHNICIAN').first()
    sup_sig = sheet.signatures.filter(role='SUPERVISOR').first()
    a0_sig = sheet.signatures.filter(role='A0_A1').first()
    
    # Logic: So sánh với phiếu cũ gần nhất
    previous_sheet = None
    differences = []
    has_previous = False
    
    if sheet.is_temporary and sheet.reverted and sheet.revert_to_sheet:
        display_data = sheet.revert_to_sheet.extracted_data
    else:
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
    
    
    
    context = {
        'sheet': sheet,
        'settings': settings,
        'reviewers': reviewers,
        'dispatchers': dispatchers,
        'technicians': technicians,
        'supervisors': supervisors,
        'tech_sig': tech_sig,
        'sup_sig': sup_sig,
        'a0_sig': a0_sig,
        'previous_sheet': previous_sheet,
        'differences': differences,
        'has_previous': has_previous,
        'added_count': added_count,
        'removed_count': removed_count,
        'changed_count': changed_count,
        'total_diff_count': total_diff_count,
        'display_data': display_data
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
            
        valid_statuses = [s[0] for s in SettingSheet.STATUS_CHOICES]
        if new_status in valid_statuses:
            sheet.status = new_status
            
        # Handle Temporary Setting
        is_temporary = request.POST.get('is_temporary') == 'on'
        valid_until_str = request.POST.get('valid_until_datetime')
        
        if is_temporary and valid_until_str:
            try:
                from django.utils.dateparse import parse_datetime
                from django.utils import timezone
                dt = parse_datetime(valid_until_str)
                if dt:
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                    sheet.is_temporary = True
                    sheet.valid_until = dt
                    
                    # Find previous sheet to revert to
                    if sheet.relay:
                        previous_sheet = SettingSheet.objects.filter(
                            relay=sheet.relay,
                            status='COMPLETED',
                            created_at__lt=sheet.created_at
                        ).order_by('-created_at').first()
                        sheet.revert_to_sheet = previous_sheet
            except Exception as e:
                print("Date parse error:", e)
        
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
        role = request.POST.get('role', 'A0_A1')
        
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
            if role == 'A0_A1' and not sup_sig_exists:
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
                sheet.status = 'PENDING_REVIEW' # Đẩy lại cho A0/A1 duyệt vận hành
                sheet.save()
            elif role == 'A0_A1' and sheet.status == 'PENDING_REVIEW':
                sheet.status = 'COMPLETED'
                sheet.save()
                
            tech_sig = sheet.signatures.filter(role='TECHNICIAN').first()
            sup_sig = sheet.signatures.filter(role='SUPERVISOR').first()
            a0_sig = sheet.signatures.filter(role='A0_A1').first()
                
            return render(request, 'sheets/partials/_signature_panel.html', {
                'sheet': sheet,
                'tech_sig': tech_sig,
                'sup_sig': sup_sig,
                'a0_sig': a0_sig
            })
            
    return JsonResponse({'success': False}, status=400)

def perform_mock_ocr(sheet):
    """Hàm chạy AI OCR (mock) trực tiếp."""
    extracted_data = []
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
                'confidence': round(conf, 1)
            })
    else:
        # Nếu không có relay hoặc relay chưa cấu hình thông số, tạo random vài thông số
        mock_params = [
            {'code': 'I_max', 'name': 'Dòng điện cắt cực đại', 'unit': 'A', 'val': round(random.uniform(10, 50), 2)},
            {'code': 'T_delay', 'name': 'Thời gian trễ', 'unit': 's', 'val': round(random.uniform(0.1, 2.0), 2)},
            {'code': 'V_min', 'name': 'Điện áp cắt thấp áp', 'unit': 'V', 'val': round(random.uniform(90, 110), 2)}
        ]
        for p in mock_params:
            conf = random.uniform(85.0, 99.9)
            extracted_data.append({
                'parameter_code': p['code'],
                'parameter_name': p['name'],
                'unit': p['unit'],
                'value': p['val'],
                'confidence': round(conf, 1)
            })
    
    sheet.extracted_data = extracted_data
    sheet.save()
    return extracted_data

@login_required
def run_mock_ocr(request, pk):
    """View giả lập quá trình chạy AI OCR (Dành cho trigger thủ công nếu cần)."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        time.sleep(1.5)
        perform_mock_ocr(sheet)
        return redirect('sheet_detail', pk=pk)
    return redirect('sheet_list')

@login_required
def sheet_save_actual_data(request, pk):
    """View cho phép KTV lưu thông số thực tế và Điều phối/A0A1 sửa lỗi OCR."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        
        is_technician = (sheet.assigned_to == request.user and sheet.status in ['RECEIVED', 'TRANSFERRED'])
        is_dispatcher_or_a0 = request.user.groups.filter(name__in=['DISPATCHER', 'A0A1']).exists()
        
        if is_technician or is_dispatcher_or_a0:
            if sheet.extracted_data:
                updated_data = []
                changes = []
                for index, item in enumerate(sheet.extracted_data):
                    # Dispatcher/A0A1 saves OCR value
                    if is_dispatcher_or_a0:
                        ocr_val = request.POST.get(f'ocr_value_{index}')
                        if ocr_val is not None and ocr_val.strip() != '':
                            try:
                                new_val = float(ocr_val)
                                old_val = float(item.get('value', 0)) if item.get('value') is not None else None
                                if old_val != new_val:
                                    changes.append(f"{item.get('parameter_code')}: {old_val} ➡️ {new_val}")
                                item['value'] = new_val
                            except ValueError:
                                pass
                                
                    # Technician saves actual value
                    if is_technician:
                        actual_val = request.POST.get(f'actual_value_{index}')
                        if actual_val is not None and actual_val.strip() != '':
                            try:
                                item['actual_value'] = float(actual_val)
                            except ValueError:
                                pass
                                
                    updated_data.append(item)
                
                sheet.extracted_data = updated_data
                sheet.save()
                
                if changes and is_dispatcher_or_a0:
                    msg = "Đã cập nhật sửa lỗi OCR: " + " | ".join(changes)
                    messages.success(request, msg)
                    
                    try:
                        from asgiref.sync import async_to_sync
                        from channels.layers import get_channel_layer
                        channel_layer = get_channel_layer()
                        if channel_layer and sheet.created_by:
                            # Gửi thông báo cho người tạo phiếu (A0A1) và người dùng khác liên quan
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
