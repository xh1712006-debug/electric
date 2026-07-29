from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from sheets.models import SettingSheet

@login_required
def get_badges_api(request):
    """API endpoint to get badge counts for real-time updates."""
    from core.context_processors import notification_badges
    data = notification_badges(request)
    return JsonResponse(data['badges'])

@login_required
def dashboard(request):
    """Trang chủ hiển thị thống kê tổng quan theo Role."""
    from django.db.models import Count
    from django.db.models.functions import TruncDate, TruncMonth
    from django.utils import timezone
    import datetime
    from sheets.models import SignatureRecord
    from django.contrib.auth.models import User
    from stations.models import Station
    from django.core.cache import cache
    import hashlib
    
    user = request.user
    cache_version = cache.get('sheet_list_version', 1)
    
    if user.is_superuser or user.groups.filter(name='ADMIN').exists():
        role = 'admin'
        period = request.GET.get('period', '7days')
        start_date_str = request.GET.get('start_date', '')
        end_date_str = request.GET.get('end_date', '')
        key_string = f"dashboard_{role}_v{cache_version}_user_{user.id}_p_{period}_sd_{start_date_str}_ed_{end_date_str}"
    elif user.groups.filter(name='DISPATCHER').exists():
        role = 'dispatcher'
        key_string = f"dashboard_{role}_v{cache_version}_user_{user.id}"
    elif user.groups.filter(name='STATION_LEADER').exists():
        role = 'station_leader'
        key_string = f"dashboard_{role}_v{cache_version}_user_{user.id}"
    elif user.groups.filter(name='SUPERVISOR').exists():
        role = 'supervisor'
        key_string = f"dashboard_{role}_v{cache_version}_user_{user.id}"
    elif user.groups.filter(name='TECHNICIAN').exists():
        role = 'technician'
        key_string = f"dashboard_{role}_v{cache_version}_user_{user.id}"
    else:
        return render(request, 'core/dashboard.html', {})
        
    cache_key = hashlib.md5(key_string.encode('utf-8')).hexdigest()
    cached_context = cache.get(cache_key)
    
    if cached_context:
        template_name = cached_context.pop('_template_name')
        return render(request, template_name, cached_context)
    
    # 1. ADMIN
    if role == 'admin':
        total_sheets = SettingSheet.objects.count()
        total_users = User.objects.count()
        total_stations = Station.objects.count()
        PENDING_ADMIN_APPROVAL = SettingSheet.objects.filter(status='PENDING_ADMIN_APPROVAL').count()
        
        # Chart Data
        today = timezone.now().date()
        chart_title = "Lưu lượng tạo Phiếu (7 ngày qua)"
        start_date = today - datetime.timedelta(days=6)
        end_date = today
        group_by = 'date'
        
        if period == 'this_month':
            start_date = today.replace(day=1)
            chart_title = "Lưu lượng tạo Phiếu (Tháng này)"
        elif period == 'this_year':
            start_date = today.replace(month=1, day=1)
            group_by = 'month'
            chart_title = "Lưu lượng tạo Phiếu (Năm nay)"
        elif period == 'custom' and start_date_str and end_date_str:
            try:
                start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
                if start_date > end_date:
                    start_date, end_date = end_date, start_date
                chart_title = f"Lưu lượng tạo Phiếu ({start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')})"
                if (end_date - start_date).days > 90:
                    group_by = 'month'
            except ValueError:
                pass
                
        start_datetime = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        end_datetime = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

        qs = SettingSheet.objects.filter(created_at__gte=start_datetime, created_at__lte=end_datetime)
        
        chart_labels = []
        chart_data = []
        
        if group_by == 'date':
            daily_counts = qs.annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).order_by('date')
            count_dict = {str(item['date']): item['count'] for item in daily_counts}
            
            delta_days = (end_date - start_date).days
            for i in range(delta_days + 1):
                d = start_date + datetime.timedelta(days=i)
                chart_labels.append(d.strftime('%d/%m'))
                chart_data.append(count_dict.get(str(d), 0))
        else: # month
            monthly_counts = qs.annotate(month=TruncMonth('created_at')).values('month').annotate(count=Count('id')).order_by('month')
            count_dict = {str(item['month'].date()): item['count'] for item in monthly_counts}
            
            curr = start_date.replace(day=1)
            while curr <= end_date:
                chart_labels.append(curr.strftime('T%m/%Y'))
                chart_data.append(count_dict.get(str(curr), 0))
                next_month = curr.month % 12 + 1
                next_year = curr.year + (curr.month // 12)
                curr = curr.replace(year=next_year, month=next_month)
            
        recent_activities = SignatureRecord.objects.select_related('sheet').order_by('-signed_at')[:5]
        _ = list(recent_activities)
        
        from categories.models import Line, Location, Project
        from stations.models import Bay, Relay
        
        context = {
            'total_sheets': total_sheets, 'total_users': total_users, 'total_stations': total_stations, 'PENDING_ADMIN_APPROVAL': PENDING_ADMIN_APPROVAL,
            'chart_labels': chart_labels, 'chart_data': chart_data, 'recent_activities': recent_activities,
            'chart_title': chart_title, 'period': period,
            'start_date': start_date_str if period == 'custom' else '',
            'end_date': end_date_str if period == 'custom' else '',
            'total_lines': Line.objects.count(),
            'total_locations': Location.objects.count(),
            'total_projects': Project.objects.count(),
            'total_bays': Bay.objects.count(),
            'total_relays': Relay.objects.count(),
            '_template_name': 'core/dashboard_admin.html'
        }
        
    # 3. DISPATCHER
    elif role == 'dispatcher':
        base_qs = SettingSheet.objects.filter(created_by=user)
        issued_count = base_qs.filter(status='ISSUED').count()
        routed_count = base_qs.filter(status='ROUTED_TO_STATION').count()
        received_count = base_qs.filter(status='RECEIVED').count()
        
        tracking_sheets = base_qs.filter(status__in=['ISSUED', 'ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED']).order_by('-created_at')[:5]
        recent_activities = SignatureRecord.objects.filter(sheet__created_by=user).select_related('sheet').order_by('-signed_at')[:5]
        recent_routed_sheets = base_qs.filter(
            status__in=['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL', 'COMPLETED'],
            relay__isnull=False
        ).select_related('relay', 'relay__bay', 'relay__bay__station').order_by('-created_at')[:15]
        
        _ = list(tracking_sheets)
        _ = list(recent_activities)
        _ = list(recent_routed_sheets)
        
        context = {
            'issued_count': issued_count, 'routed_count': routed_count, 'received_count': received_count,
            'tracking_sheets': tracking_sheets, 'recent_activities': recent_activities,
            'recent_routed_sheets': recent_routed_sheets,
            '_template_name': 'core/dashboard_dispatcher.html'
        }

    # STATION_LEADER
    elif role == 'station_leader':
        my_station = None
        if hasattr(user, 'userprofile') and user.userprofile.station:
            my_station = user.userprofile.station

        if my_station:
            from django.db.models import Q
            base_qs = SettingSheet.objects.filter(Q(station=my_station) | Q(relay__bay__station=my_station)).distinct()
            from django.db.models import Count, Q
            station_techs = User.objects.filter(
                groups__name='TECHNICIAN', 
                userprofile__station=my_station
            ).annotate(
                active_tasks=Count('assigned_sheets', filter=Q(assigned_sheets__status__in=['TRANSFERRED', 'RECEIVED']))
            ).order_by('active_tasks')
        else:
            base_qs = SettingSheet.objects.none()
            station_techs = []

        pending_assign = base_qs.filter(status='ROUTED_TO_STATION').count()
        in_progress = base_qs.filter(status__in=['TRANSFERRED', 'RECEIVED']).count()
        PENDING_ADMIN_APPROVAL = base_qs.filter(status='PENDING_ADMIN_APPROVAL').count()
        completed = base_qs.filter(status='COMPLETED').count()

        recent_sheets = base_qs.filter(status__in=['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL']).order_by('-created_at')[:8]
        doughnut_data = [pending_assign, in_progress, PENDING_ADMIN_APPROVAL, completed]
        
        _ = list(station_techs) if hasattr(station_techs, '__iter__') else station_techs
        _ = list(recent_sheets)
        
        context = {
            'my_station': my_station,
            'pending_assign': pending_assign,
            'in_progress': in_progress,
            'PENDING_ADMIN_APPROVAL': PENDING_ADMIN_APPROVAL,
            'completed': completed,
            'recent_sheets': recent_sheets,
            'doughnut_data': doughnut_data,
            'station_techs': station_techs,
            '_template_name': 'core/dashboard_station_leader.html'
        }

    # 4. SUPERVISOR
    elif role == 'supervisor':
        my_station = None
        if hasattr(user, 'userprofile') and user.userprofile.station:
            my_station = user.userprofile.station

        if my_station:
            from django.db.models import Q
            base_qs = SettingSheet.objects.filter(Q(station=my_station) | Q(relay__bay__station=my_station)).distinct()
            active_techs = User.objects.filter(groups__name='TECHNICIAN', userprofile__station=my_station).count()
        else:
            base_qs = SettingSheet.objects.none()
            active_techs = 0

        pending_supervision = base_qs.filter(status='RECEIVED').count()
        PENDING_ADMIN_APPROVAL = base_qs.filter(status='PENDING_ADMIN_APPROVAL').count()
        completed = base_qs.filter(status='COMPLETED').count()
        
        recent_sheets = base_qs.filter(status__in=['TRANSFERRED', 'RECEIVED', 'PENDING_ADMIN_APPROVAL']).order_by('-created_at')[:8]
        _ = list(recent_sheets)
        
        context = {
            'my_station': my_station,
            'active_techs': active_techs, 
            'pending_supervision': pending_supervision,
            'PENDING_ADMIN_APPROVAL': PENDING_ADMIN_APPROVAL,
            'completed': completed,
            'recent_sheets': recent_sheets,
            '_template_name': 'core/dashboard_supervisor.html'
        }

    # 5. TECHNICIAN
    elif role == 'technician':
        my_station = None
        if hasattr(user, 'userprofile') and user.userprofile.station:
            my_station = user.userprofile.station

        assigned_sheets = SettingSheet.objects.filter(assigned_to=request.user)
        new_sheets = assigned_sheets.filter(status='TRANSFERRED').count()
        in_progress = assigned_sheets.filter(status='RECEIVED').count()
        completed = assigned_sheets.filter(status__in=['PENDING_ADMIN_APPROVAL', 'COMPLETED']).count()
        
        recent_sheets = assigned_sheets.exclude(status='COMPLETED').order_by('-created_at')[:8]
        _ = list(recent_sheets)
        
        context = {
            'my_station': my_station,
            'new_sheets': new_sheets, 
            'in_progress': in_progress, 
            'completed': completed,
            'recent_sheets': recent_sheets,
            '_template_name': 'core/dashboard_technician.html'
        }
        
    cache.set(cache_key, context, timeout=86400)
    template_name = context.pop('_template_name')
    return render(request, template_name, context)

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
        "DISPATCHER": "Điều phối viên (kiêm Rà soát)",
        "STATION_LEADER": "Trưởng nhóm Trạm",
        "TECHNICIAN": "Kỹ thuật viên",
        "SUPERVISOR": "Giám sát trạm"
    }
    for g in groups:
        g.vi_name = GROUP_NAMES_VI.get(g.name, g.name)
        
    for u in users:
        for g in u.groups.all():
            g.vi_name = GROUP_NAMES_VI.get(g.name, g.name)
    from django.core.paginator import Paginator
    from stations.models import Station
    paginator = Paginator(users, 30)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
            
    return render(request, 'core/user_list.html', {
        'users': page_obj,
        'groups': groups,
        'stations': Station.objects.all()
    })

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        password = request.POST.get('password')
        group_id = request.POST.get('group')
        station_id = request.POST.get('station_id')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Tên đăng nhập đã tồn tại!')
        else:
            user = User.objects.create_user(username=username, email=email, password=password, first_name=first_name)
            if group_id:
                group = Group.objects.get(id=group_id)
                user.groups.add(group)
            
            if station_id:
                from stations.models import Station
                from core.models import UserProfile
                try:
                    station = Station.objects.get(id=station_id)
                    profile, created = UserProfile.objects.get_or_create(user=user)
                    profile.station = station
                    profile.save()
                except Exception as e:
                    pass

            messages.success(request, 'Tạo tài khoản thành công!')
        return redirect('user_list')
    return HttpResponse("Invalid request")

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def user_update(request, user_id):
    if request.method == 'POST':
        from django.shortcuts import get_object_or_404
        user = get_object_or_404(User, id=user_id)
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        password = request.POST.get('password')
        group_id = request.POST.get('group')
        station_id = request.POST.get('station_id')

        user.email = email
        user.first_name = first_name
        if password:
            user.set_password(password)
        
        if group_id:
            group = Group.objects.get(id=group_id)
            user.groups.clear()
            user.groups.add(group)
            
            # Handle station id for specific groups
            if station_id and group.name in ['TECHNICIAN', 'SUPERVISOR', 'STATION_LEADER']:
                from stations.models import Station
                from core.models import UserProfile
                try:
                    station = Station.objects.get(id=station_id)
                    profile, created = UserProfile.objects.get_or_create(user=user)
                    profile.station = station
                    profile.save()
                    print(f"Saved station {station} for {user.username}")
                except Exception as e:
                    print(f"Error saving station: {e}")
            else:
                from core.models import UserProfile
                print(f"Clearing station for {user.username} (station_id: {station_id}, group: {group.name})")
                UserProfile.objects.filter(user=user).update(station=None)
        
        user.save()
        messages.success(request, 'Cập nhật tài khoản thành công!')
        return redirect('user_list')
    return HttpResponse("Invalid request")

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def user_toggle_status(request, user_id):
    if request.method == 'POST':
        from django.shortcuts import get_object_or_404
        user = get_object_or_404(User, id=user_id)
        if user != request.user:
            user.is_active = not user.is_active
            user.save()
            status_msg = "mở khóa" if user.is_active else "khóa"
            messages.success(request, f'Đã {status_msg} tài khoản {user.username}.')
        else:
            messages.error(request, 'Bạn không thể tự khóa tài khoản của mình.')
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
        "can_dispatch_sheet": "Nút: Chuyển Trạm / Phân công Đội",
        "can_execute_sheet": "Nút: Tiếp nhận & Ký Thực thi (KTV)",
        "can_supervise_sheet": "Nút: Ký Nghiệm thu (Giám sát trạm)",
    }
    
    GROUP_NAMES_VI = {
        "ADMIN": "Quản trị viên",
        "DISPATCHER": "Điều phối viên",
        "STATION_LEADER": "Trưởng nhóm Trạm",
        "TECHNICIAN": "Kỹ thuật viên",
        "SUPERVISOR": "Giám sát trạm"
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

@login_required
def dispatcher_routed_relays(request):
    """Trang xem tất cả các rơ-le có phiếu mới nhất đã được duyệt về trạm."""
    if not request.user.groups.filter(name='DISPATCHER').exists() and not request.user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
        
    from sheets.models import SettingSheet
    # Lấy các phiếu có rơ-le và đã được Admin phê duyệt (COMPLETED)
    all_routed_sheets = SettingSheet.objects.filter(
        status='COMPLETED',
        relay__isnull=False
    )
    if not request.user.is_superuser:
        all_routed_sheets = all_routed_sheets.filter(created_by=request.user)
        
    all_routed_sheets = all_routed_sheets.select_related('relay', 'relay__bay', 'relay__bay__station').order_by('-created_at')
    
    # Lọc unique rơ-le (chỉ lấy phiếu mới nhất của mỗi rơ-le đã duyệt)
    seen_relays = set()
    unique_routed_sheets = []
    for sheet in all_routed_sheets:
        if sheet.relay_id not in seen_relays:
            unique_routed_sheets.append(sheet)
            seen_relays.add(sheet.relay_id)
            
    # Phân trang
    from django.core.paginator import Paginator
    paginator = Paginator(unique_routed_sheets, 40)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'core/routed_relays.html', {'sheets': page_obj})

@login_required
def profile(request):
    """Trang xem thông tin tài khoản cá nhân."""
    return render(request, 'core/profile.html')

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def system_config_view(request):
    """Trang cấu hình hệ thống (API Endpoints động)."""
    from .models import SystemConfig
    
    # Init default configs if they don't exist
    default_configs = [
        ('API_DANH_MUC_DON_VI_QUAN_LY', 'http://localhost:8000/api/v1/categories/management-units/', 'Endpoint API Đơn vị quản lý'),
        ('API_DANH_MUC_NUOC_SAN_XUAT', 'http://localhost:8000/api/v1/categories/manufacturing-countries/', 'Endpoint API Nước sản xuất'),
        ('API_DANH_MUC_HANG_SAN_XUAT', 'http://localhost:8000/api/v1/categories/manufacturers/', 'Endpoint API Hãng sản xuất'),
        ('API_DANH_MUC_SO_HUU', 'http://localhost:8000/api/v1/categories/ownerships/', 'Endpoint API Sở hữu'),
        ('API_DANH_MUC_CAP_DIEN_AP', 'http://localhost:8000/api/v1/categories/voltage-levels/', 'Endpoint API Cấp điện áp'),
        ('API_DANH_MUC_LOAI_THIET_BI', 'http://localhost:8000/api/v1/categories/equipment-types/', 'Endpoint API Loại thiết bị'),
        ('API_DANH_MUC_TRANG_THAI', 'http://localhost:8000/api/v1/categories/operational-statuses/', 'Endpoint API Trạng thái vận hành'),
        ('API_DANH_MUC_DUONG_DAY', 'http://localhost:8000/api/v1/categories/lines/', 'Endpoint API Đường dây'),
        ('API_DANH_MUC_CONG_TRINH', 'http://localhost:8000/api/v1/categories/projects/', 'Endpoint API Công trình'),
        ('API_DANH_MUC_VI_TRI', 'http://localhost:8000/api/v1/categories/locations/', 'Endpoint API Vị trí'),
        ('API_TRAM', 'http://localhost:8000/api/v1/categories/stations/', 'Endpoint API Trạm'),
        ('API_NGAN_LO', 'http://localhost:8000/api/v1/categories/bays/', 'Endpoint API Ngăn lộ'),
        ('API_THIET_BI', 'http://localhost:8000/api/v1/categories/equipments/', 'Endpoint API Thiết bị (Relay)'),
    ]
    
    for key, val, desc in default_configs:
        SystemConfig.objects.get_or_create(key=key, defaults={'value': val, 'description': desc})
        
    configs = SystemConfig.objects.all().order_by('-id')
    return render(request, 'core/system_config.html', {'configs': configs})

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def system_config_create(request):
    if request.method == 'POST':
        from .models import SystemConfig
        import time
        key = request.POST.get('key', '').strip()
        value = request.POST.get('value', '').strip()
        description = request.POST.get('description', '')
        auth_header = request.POST.get('auth_header', '').strip()
        
        if not key:
            key = f"API_AUTO_{int(time.time())}"
            
        if value:
            SystemConfig.objects.create(
                key=key.upper(),
                value=value,
                description=description,
                auth_header=auth_header
            )
            messages.success(request, f"Đã thêm API mới: {key.upper()}")
        return redirect('system_config')
    return redirect('system_config')

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def system_config_bulk_create(request):
    if request.method == 'POST':
        from .models import SystemConfig
        import time
        urls_text = request.POST.get('urls', '')
        urls = [u.strip() for u in urls_text.split('\n') if u.strip().startswith('http')]
        count = 0
        for idx, url in enumerate(urls):
            key = f"API_AUTO_{int(time.time())}_{idx}"
            SystemConfig.objects.create(key=key, value=url, description="Bulk imported")
            count += 1
        if count > 0:
            messages.success(request, f"Đã thêm hàng loạt {count} API thành công!")
        else:
            messages.warning(request, "Không tìm thấy URL hợp lệ nào.")
        return redirect('system_config')
    return redirect('system_config')

def render_system_config_row(config):
    from django.urls import reverse
    sync_url = reverse('api_sync_endpoint')
    delete_url = reverse('system_config_delete', args=[config.id])
    
    val_esc = (config.value or "").replace("'", "\\'")
    key_esc = (config.key or "").replace("'", "\\'")
    desc_esc = (config.description or "").replace("'", "\\'")
    auth_esc = (config.auth_header or "").replace("'", "\\'")
    
    last_sync_html = f'<div class="text-[10px] text-slate-500 mt-1" title="{config.last_sync_status}">Lần cuối: {config.last_sync_time.strftime("%d/%m/%Y %H:%M")}</div>' if config.last_sync_time else ''
    sync_count_html = f'<div class="text-[10px] text-blue-500 mt-1 font-semibold">Đã đồng bộ: {config.sync_count} lần</div>'
    
    sync_interval = config.sync_interval_minutes
    if sync_interval >= 525600 and sync_interval % 525600 == 0:
        interval_str = f"{sync_interval // 525600} năm"
    elif sync_interval >= 43200 and sync_interval % 43200 == 0:
        interval_str = f"{sync_interval // 43200} tháng"
    elif sync_interval >= 1440 and sync_interval % 1440 == 0:
        interval_str = f"{sync_interval // 1440} ngày"
    elif sync_interval >= 60 and sync_interval % 60 == 0:
        interval_str = f"{sync_interval // 60} giờ"
    else:
        interval_str = f"{sync_interval} phút"

    if config.is_syncing:
        sync_col_html = f'''
            <div class="inline-flex items-center px-2 py-1 bg-amber-50 text-amber-700 text-xs font-medium rounded border border-amber-200 mb-1">
                <i class="fas fa-sync-alt fa-spin mr-1"></i> Đang đồng bộ...
            </div>
            {sync_count_html}
        '''
    else:
        sync_col_html = f'''
            <div class="inline-flex items-center px-2 py-1 bg-emerald-50 text-emerald-700 text-xs font-medium rounded border border-emerald-200 mb-1">
                <i class="fas fa-clock mr-1"></i> Bật (Mỗi {interval_str})
            </div>
            {last_sync_html}
            {sync_count_html}
        ''' if config.auto_sync_enabled else f'''
            <div class="inline-flex items-center px-2 py-1 bg-slate-50 text-slate-500 text-xs font-medium rounded border border-slate-200">
                <i class="fas fa-power-off mr-1"></i> Tắt
            </div>
            {last_sync_html}
            {sync_count_html}
        '''

    sync_btn_html = f'''
        <button type="button" disabled class="group text-xs font-semibold text-slate-400 bg-slate-50 px-2.5 py-1.5 rounded-lg border border-slate-200 cursor-not-allowed flex items-center shadow-sm" title="Đang đồng bộ ngầm">
            <i class="fas fa-sync-alt fa-spin mr-1"></i> Đang đồng bộ...
        </button>
    ''' if config.is_syncing else f'''
        <button type="button" 
                hx-post="{sync_url}" 
                hx-vals='{{"config_id": "{config.id}"}}'
                hx-target="#sync-result-{config.id}"
                hx-swap="outerHTML"
                class="group text-xs font-semibold text-emerald-600 hover:text-white hover:bg-emerald-500 bg-emerald-50 px-2.5 py-1.5 rounded-lg border border-emerald-200 transition-colors flex items-center shadow-sm" title="Đồng bộ ngay">
            <i class="fas fa-sync-alt mr-1 group-[.htmx-request]:animate-spin"></i> <span class="group-[.htmx-request]:hidden">Đồng bộ</span><span class="hidden group-[.htmx-request]:inline ml-1">Đang tải...</span>
        </button>
    '''

    return f'''
    <td class="px-6 py-3 font-medium text-slate-900">{config.key}</td>
    <td class="px-6 py-3">
        <div class="text-blue-600 font-mono text-sm break-all">{config.value}</div>
        <div id="sync-result-{config.id}"></div>
    </td>
    <td class="px-6 py-3 text-slate-500">{config.description}</td>
    <td class="px-6 py-3">
        {sync_col_html}
    </td>
    <td class="px-6 py-3 text-right">
        <div class="flex items-center justify-end gap-2">
            {sync_btn_html}
            <button type="button" onclick="openEditModal({config.id}, '{key_esc}', '{val_esc}', '{desc_esc}', '{auth_esc}', '{config.auto_sync_enabled}', {config.sync_interval_minutes})" class="text-slate-400 hover:text-blue-600 transition-colors p-1" title="Sửa">
                <i class="fas fa-edit text-base"></i>
            </button>
            <button type="button" 
                    hx-post="{delete_url}" 
                    hx-confirm="Bạn có chắc chắn muốn xoá cấu hình API này?"
                    hx-target="#config-row-{config.id}"
                    hx-swap="outerHTML"
                    class="text-slate-400 hover:text-red-500 transition-colors p-1" title="Xoá">
                <i class="fas fa-trash-alt text-base"></i>
            </button>
        </div>
    </td>
    '''

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def system_config_delete(request, config_id):
    if request.method in ['POST', 'DELETE']:
        from .models import SystemConfig
        SystemConfig.objects.filter(id=config_id).delete()
        return HttpResponse("")
    return HttpResponseForbidden()

@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def system_config_update(request):
    if request.method == 'POST':
        from .models import SystemConfig
        config_id = request.POST.get('config_id')
        new_value = request.POST.get('value')
        new_key = request.POST.get('key')
        new_desc = request.POST.get('description')
        new_auth = request.POST.get('auth_header')
        
        auto_sync_enabled = request.POST.get('auto_sync_enabled') == 'on'
        sync_interval_minutes = request.POST.get('sync_interval_minutes')
        
        try:
            config = SystemConfig.objects.get(id=config_id)
            if new_value is not None:
                config.value = new_value.strip()
            if new_key:
                config.key = new_key.strip().upper()
            if new_desc is not None:
                config.description = new_desc.strip()
            if new_auth is not None:
                config.auth_header = new_auth.strip()
                
            config.auto_sync_enabled = auto_sync_enabled
            if sync_interval_minutes:
                try:
                    config.sync_interval_minutes = int(sync_interval_minutes)
                except ValueError:
                    pass
                    
            config.save()
            return HttpResponse(render_system_config_row(config))
        except SystemConfig.DoesNotExist:
            return HttpResponseForbidden("Not found")
            
@login_required
@permission_required('sheets.can_manage_users', raise_exception=True)
def system_config_row(request, config_id):
    from .models import SystemConfig
    try:
        config = SystemConfig.objects.get(id=config_id)
        return HttpResponse(render_system_config_row(config))
    except SystemConfig.DoesNotExist:
        return HttpResponseForbidden("Not found")
@login_required
def api_sync_endpoint(request):
    import json
    import urllib.request
    from categories.models import ManagementUnit, ManufacturingCountry, Manufacturer, Ownership, VoltageLevel, EquipmentType, OperationalStatus, Line, Project, Location
    from core.utils.xml_converter import json_to_xml
    import logging
    from core.models import SystemConfig
    from django.http import HttpResponse, HttpResponseForbidden
    
    if not (request.user.is_superuser or request.user.groups.filter(name='ADMIN').exists()):
        return HttpResponseForbidden("Access Denied")
        
    logger = logging.getLogger(__name__)

    if request.method == 'POST':
        config_id = request.POST.get('config_id')
        try:
            config = SystemConfig.objects.get(id=config_id)
            from core.utils.api_sync import run_api_sync
            success, count, error_message = run_api_sync(config_id=config_id)
            
            # Increment count for manual syncs too
            config.sync_count += 1
            config.save(update_fields=['sync_count'])
            
            if not success:
                return HttpResponse(f'''
                <div id="sync-result-{config_id}" class="text-xs text-red-600 font-medium mt-2 p-2 bg-red-50 border border-red-100 rounded">
                    <i class="fas fa-exclamation-circle mr-1"></i> {error_message}
                </div>
                ''', status=200)
                
            return HttpResponse(f'''
            <div id="sync-result-{config.id}" class="text-xs text-emerald-600 font-medium mt-2 p-2 bg-emerald-50 border border-emerald-100 rounded flex items-center justify-between">
                <div><i class="fas fa-check-circle mr-1"></i> Đã đồng bộ <b>{count}</b> bản ghi.</div>
                <span class="text-[10px] text-emerald-500 bg-white px-2 py-0.5 rounded border border-emerald-200">XML Exported</span>
            </div>
            ''')
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = str(e).replace('<', '&lt;').replace('>', '&gt;')
            return HttpResponse(f'''
            <div id="sync-result-{config_id}" class="text-xs text-red-600 font-medium mt-2 p-2 bg-red-50 border border-red-100 rounded">
                <i class="fas fa-exclamation-circle mr-1"></i> Lỗi đồng bộ: {error_msg}
            </div>
            ''', status=200)
    return HttpResponse("Invalid request", status=400)
