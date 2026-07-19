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
        sheets = sheets.filter(status=status_filter)

    paginator = Paginator(sheets, 40)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'sheets': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'list_title': 'Tất cả Phiếu Chỉnh định'
    }
    return render(request, 'sheets/sheet_list.html', context)

@login_required
def my_sheets(request):
    """View danh sách phiếu của tôi."""
    # Lấy các phiếu do mình tạo hoặc được assign cho mình
    from django.db.models import Q
    sheets = SettingSheet.objects.filter(
        Q(created_by=request.user) | Q(assigned_to=request.user)
    ).order_by('-created_at')
    
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    
    from django.core.paginator import Paginator

    if search_query:
        sheets = sheets.filter(sheet_code__icontains=search_query)
        
    if status_filter:
        sheets = sheets.filter(status=status_filter)

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
    
    tech_sig = sheet.signatures.filter(role='TECHNICIAN').first()
    sup_sig = sheet.signatures.filter(role='SUPERVISOR').first()
    a0_sig = sheet.signatures.filter(role='A0_A1').first()
    
    context = {
        'sheet': sheet,
        'settings': settings,
        'reviewers': reviewers,
        'dispatchers': dispatchers,
        'technicians': technicians,
        'tech_sig': tech_sig,
        'sup_sig': sup_sig,
        'a0_sig': a0_sig
    }
    return render(request, 'sheets/sheet_detail.html', context)

@login_required
def sheet_assign(request, pk):
    """View API dùng HTMX để giao phiếu cho người khác."""
    if request.method == 'POST':
        sheet = get_object_or_404(SettingSheet, pk=pk)
        assignee_id = request.POST.get('assignee_id')
        new_status = request.POST.get('status')
        
        from django.contrib.auth.models import User
        if assignee_id:
            user = get_object_or_404(User, pk=assignee_id)
            sheet.assigned_to = user
        else:
            sheet.assigned_to = None
            
        valid_statuses = [s[0] for s in SettingSheet.STATUS_CHOICES]
        if new_status in valid_statuses:
            sheet.status = new_status
            
        sheet.save()
        messages.success(request, f"Đã giao phiếu cho {sheet.assigned_to.first_name or sheet.assigned_to.username if sheet.assigned_to else 'Không ai'}")
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
