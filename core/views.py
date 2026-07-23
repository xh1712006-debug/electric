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
        
        context = {
            'total_sheets': total_sheets, 'total_users': total_users, 'total_stations': total_stations, 'PENDING_ADMIN_APPROVAL': PENDING_ADMIN_APPROVAL,
            'chart_labels': chart_labels, 'chart_data': chart_data, 'recent_activities': recent_activities,
            'chart_title': chart_title, 'period': period,
            'start_date': start_date_str if period == 'custom' else '',
            'end_date': end_date_str if period == 'custom' else '',
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
