from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.contrib import messages
from sheets.models import SettingSheet

@login_required
def dashboard(request):
    """Trang chủ hiển thị thống kê tổng quan theo Role."""
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    from django.utils import timezone
    import datetime
    from sheets.models import SignatureRecord
    from django.contrib.auth.models import User
    from stations.models import Station
    
    user = request.user
    
    # 1. ADMIN
    if user.is_superuser or user.groups.filter(name='ADMIN').exists():
        total_sheets = SettingSheet.objects.count()
        total_users = User.objects.count()
        total_stations = Station.objects.count()
        pending_review = SettingSheet.objects.filter(status='PENDING_REVIEW').count()
        
        # Chart Data
        today = timezone.now().date()
        week_ago = today - datetime.timedelta(days=6)
        daily_counts = SettingSheet.objects.filter(created_at__date__gte=week_ago).annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).order_by('date')
        count_dict = {str(item['date']): item['count'] for item in daily_counts}
        
        chart_labels = []
        chart_data = []
        for i in range(7):
            d = week_ago + datetime.timedelta(days=i)
            chart_labels.append(d.strftime('%d/%m'))
            chart_data.append(count_dict.get(str(d), 0))
            
        recent_activities = SignatureRecord.objects.select_related('sheet').order_by('-signed_at')[:5]
        
        context = {
            'total_sheets': total_sheets, 'total_users': total_users, 'total_stations': total_stations, 'pending_review': pending_review,
            'chart_labels': chart_labels, 'chart_data': chart_data, 'recent_activities': recent_activities
        }
        return render(request, 'core/dashboard_admin.html', context)
        
    # 2. A0A1 (Người tạo phiếu)
    elif user.groups.filter(name='A0A1').exists():
        created_today = SettingSheet.objects.filter(created_at__date=timezone.now().date()).count()
        total_active = SettingSheet.objects.exclude(status__in=['COMPLETED', 'DRAFT']).count()
        
        status_counts = SettingSheet.objects.values('status').annotate(count=Count('id'))
        status_dict = {item['status']: item['count'] for item in status_counts}
        doughnut_data = [
            status_dict.get('ISSUED', 0),
            status_dict.get('COMPLETED', 0),
            status_dict.get('TRANSFERRED', 0) + status_dict.get('RECEIVED', 0)
        ]
        
        recent_sheets = SettingSheet.objects.all().order_by('-created_at')[:5]
        
        context = {
            'created_today': created_today, 'total_active': total_active,
            'doughnut_data': doughnut_data, 'recent_sheets': recent_sheets
        }
        return render(request, 'core/dashboard_a0.html', context)

    # 3. DISPATCHER (Rà soát & Giao việc)
    elif user.groups.filter(name='DISPATCHER').exists():
        issued_count = SettingSheet.objects.filter(status='ISSUED').count() # Chờ rà soát
        reviewed_count = SettingSheet.objects.filter(status='REVIEWED').count() # Chờ giao KTV
        received_count = SettingSheet.objects.filter(status='RECEIVED').count() # KTV đang làm
        
        tracking_sheets = SettingSheet.objects.filter(status__in=['ISSUED', 'REVIEWED', 'TRANSFERRED', 'RECEIVED']).order_by('-created_at')[:5]
        recent_activities = SignatureRecord.objects.select_related('sheet').order_by('-signed_at')[:5]
        
        context = {
            'issued_count': issued_count, 'reviewed_count': reviewed_count, 'received_count': received_count,
            'tracking_sheets': tracking_sheets, 'recent_activities': recent_activities
        }
        return render(request, 'core/dashboard_dispatcher.html', context)

    # 4. SUPERVISOR
    elif user.groups.filter(name='SUPERVISOR').exists():
        # Lọc các trạm mà supervisor quản lý (giả sử tất cả trạm tạm thời nếu chưa mapping)
        stations_count = Station.objects.count()
        active_techs = User.objects.filter(groups__name='TECHNICIAN').count()
        pending_supervision = SettingSheet.objects.filter(status='RECEIVED').count()
        
        recent_sheets = SettingSheet.objects.filter(status__in=['RECEIVED', 'PENDING_REVIEW']).order_by('-created_at')[:5]
        
        context = {
            'stations_count': stations_count, 'active_techs': active_techs, 'pending_supervision': pending_supervision,
            'recent_sheets': recent_sheets
        }
        return render(request, 'core/dashboard_supervisor.html', context)

    # 5. TECHNICIAN
    elif user.groups.filter(name='TECHNICIAN').exists():
        assigned_sheets = SettingSheet.objects.filter(assigned_to=request.user)
        new_sheets = assigned_sheets.filter(status='TRANSFERRED').count()
        in_progress = assigned_sheets.filter(status='RECEIVED').count()
        completed = assigned_sheets.filter(status__in=['COMPLETED', 'REVIEWED']).count()
        
        recent_sheets = assigned_sheets.exclude(status='COMPLETED').order_by('-created_at')[:5]
        recent_activities = SignatureRecord.objects.filter(signer_name=request.user.get_full_name() or request.user.username).select_related('sheet').order_by('-signed_at')[:5]
        
        status_counts = assigned_sheets.values('status').annotate(count=Count('id'))
        status_dict = {item['status']: item['count'] for item in status_counts}
        doughnut_data = [
            status_dict.get('TRANSFERRED', 0),
            status_dict.get('RECEIVED', 0),
            status_dict.get('PENDING_REVIEW', 0) + status_dict.get('COMPLETED', 0)
        ]
        
        context = {
            'new_sheets': new_sheets, 'in_progress': in_progress, 'completed': completed,
            'recent_sheets': recent_sheets, 'doughnut_data': doughnut_data, 'recent_activities': recent_activities
        }
        return render(request, 'core/dashboard_technician.html', context)
        
    else:
        return render(request, 'core/dashboard.html', {})


@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def user_list(request):
    from django.db.models import Q
    search_query = request.GET.get('search', '')
    
    users = User.objects.all().prefetch_related('groups').order_by('-date_joined')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) | 
            Q(first_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
        
    groups = Group.objects.all()
    
    GROUP_NAMES_VI = {
        "ADMIN": "Quản trị viên",
        "A0A1": "Điều độ A0/A1",
        "DISPATCHER": "Điều độ viên (kiêm Rà soát)",
        "TECHNICIAN": "Kỹ thuật viên",
        "SUPERVISOR": "Giám sát trạm",
    }
    for g in groups:
        g.vi_name = GROUP_NAMES_VI.get(g.name, g.name)
        
    for u in users:
        for g in u.groups.all():
            g.vi_name = GROUP_NAMES_VI.get(g.name, g.name)
    from django.core.paginator import Paginator
    paginator = Paginator(users, 30)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
            
    return render(request, 'core/user_list.html', {'users': page_obj, 'groups': groups})

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        password = request.POST.get('password')
        group_id = request.POST.get('group')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Tên đăng nhập đã tồn tại!')
        else:
            user = User.objects.create_user(username=username, email=email, password=password, first_name=first_name)
            if group_id:
                group = Group.objects.get(id=group_id)
                user.groups.add(group)
            messages.success(request, 'Tạo tài khoản thành công!')
        return redirect('user_list')
    return HttpResponse("Invalid request")

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def role_matrix(request):
    groups = Group.objects.all().order_by('id')
    content_type = ContentType.objects.get_for_model(SettingSheet)
    # Filter only custom permissions for the matrix
    custom_perms_codenames = [
        "can_view_stations", "can_view_checks", "can_manage_users", "can_create_sheet",
        "can_approve_sheet", "can_dispatch_sheet", "can_execute_sheet",
        "can_supervise_sheet"
    ]
    permissions = Permission.objects.filter(content_type=content_type, codename__in=custom_perms_codenames).order_by('id')
    
    PERM_NAMES_VI = {
        "can_view_stations": "Truy cập Quản lý Trạm",
        "can_view_checks": "Truy cập Kiểm tra Định kỳ",
        "can_manage_users": "Quản trị Hệ thống (Tài khoản & Phân quyền)",
        "can_create_sheet": "Tạo Phiếu chỉnh định & Chạy AI OCR",
        "can_approve_sheet": "Nút: Phê duyệt Lệnh",
        "can_dispatch_sheet": "Nút: Phân phối Phiếu cho KTV",
        "can_execute_sheet": "Nút: Tiếp nhận & Ký Thực thi (KTV)",
        "can_supervise_sheet": "Nút: Ký Nghiệm thu (Giám sát trạm)",
    }
    
    GROUP_NAMES_VI = {
        "ADMIN": "Quản trị viên",
        "A0A1": "Điều độ A0/A1",
        "DISPATCHER": "Điều độ viên (kiêm Rà soát)",
        "TECHNICIAN": "Kỹ thuật viên",
        "SUPERVISOR": "Giám sát trạm",
    }
    
    # Inject vi_name directly into the permission object for easy template access
    for perm in permissions:
        perm.vi_name = PERM_NAMES_VI.get(perm.codename, perm.name)
        
    for group in groups:
        group.vi_name = GROUP_NAMES_VI.get(group.name, group.name)
    
    # Pre-calculate matrix state
    matrix = {}
    for group in groups:
        matrix[group.id] = list(group.permissions.values_list('id', flat=True))

    return render(request, 'core/role_matrix.html', {
        'groups': groups,
        'permissions': permissions,
        'matrix': matrix
    })

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def role_matrix_update(request):
    if request.method == 'POST':
        group_id = request.POST.get('group_id')
        perm_id = request.POST.get('perm_id')
        action = request.POST.get('action') # 'add' or 'remove'
        
        group = Group.objects.get(id=group_id)
        perm = Permission.objects.get(id=perm_id)
        
        if action == 'add':
            group.permissions.add(perm)
        else:
            group.permissions.remove(perm)
            
        return HttpResponse("""<i class="fas fa-check text-green-500"></i>""", status=200)
    return HttpResponse("Error", status=400)
