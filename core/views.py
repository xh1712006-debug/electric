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

    # 3. DISPATCHER (Rà soát & Điều phối về Trạm)
    elif user.groups.filter(name='DISPATCHER').exists():
        issued_count = SettingSheet.objects.filter(status='ISSUED').count() # Chờ rà soát
        routed_count = SettingSheet.objects.filter(status='ROUTED_TO_STATION').count() # Đã chuyển về trạm
        received_count = SettingSheet.objects.filter(status='RECEIVED').count() # KTV đang làm
        
        tracking_sheets = SettingSheet.objects.filter(status__in=['ISSUED', 'ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED']).order_by('-created_at')[:5]
        recent_activities = SignatureRecord.objects.select_related('sheet').order_by('-signed_at')[:5]
        
        context = {
            'issued_count': issued_count, 'routed_count': routed_count, 'received_count': received_count,
            'tracking_sheets': tracking_sheets, 'recent_activities': recent_activities
        }
        return render(request, 'core/dashboard_dispatcher.html', context)

    # STATION_LEADER
    elif user.groups.filter(name='STATION_LEADER').exists():
        my_station = None
        if hasattr(user, 'userprofile') and user.userprofile.station:
            my_station = user.userprofile.station

        if my_station:
            from django.db.models import Q
            base_qs = SettingSheet.objects.filter(Q(station=my_station) | Q(relay__bay__station=my_station)).distinct()
            
            # Get technicians in this station and annotate with active sheets
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
        pending_review = base_qs.filter(status='PENDING_REVIEW').count()
        completed = base_qs.filter(status='COMPLETED').count()

        recent_sheets = base_qs.filter(status__in=['ROUTED_TO_STATION', 'TRANSFERRED', 'RECEIVED', 'PENDING_REVIEW']).order_by('-created_at')[:8]
        
        doughnut_data = [pending_assign, in_progress, pending_review, completed]
        
        context = {
            'my_station': my_station,
            'pending_assign': pending_assign,
            'in_progress': in_progress,
            'pending_review': pending_review,
            'completed': completed,
            'recent_sheets': recent_sheets,
            'doughnut_data': doughnut_data,
            'station_techs': station_techs
        }
        return render(request, 'core/dashboard_station_leader.html', context)

    # 4. SUPERVISOR
    elif user.groups.filter(name='SUPERVISOR').exists():
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
        pending_review = base_qs.filter(status='PENDING_REVIEW').count()
        completed = base_qs.filter(status='COMPLETED').count()
        
        recent_sheets = base_qs.filter(status__in=['TRANSFERRED', 'RECEIVED', 'PENDING_REVIEW']).order_by('-created_at')[:8]
        
        context = {
            'my_station': my_station,
            'active_techs': active_techs, 
            'pending_supervision': pending_supervision,
            'pending_review': pending_review,
            'completed': completed,
            'recent_sheets': recent_sheets
        }
        return render(request, 'core/dashboard_supervisor.html', context)

    # 5. TECHNICIAN
    elif user.groups.filter(name='TECHNICIAN').exists():
        my_station = None
        if hasattr(user, 'userprofile') and user.userprofile.station:
            my_station = user.userprofile.station

        assigned_sheets = SettingSheet.objects.filter(assigned_to=request.user)
        new_sheets = assigned_sheets.filter(status='TRANSFERRED').count()
        in_progress = assigned_sheets.filter(status='RECEIVED').count()
        completed = assigned_sheets.filter(status__in=['PENDING_REVIEW', 'COMPLETED']).count()
        
        recent_sheets = assigned_sheets.exclude(status='COMPLETED').order_by('-created_at')[:8]
        
        context = {
            'my_station': my_station,
            'new_sheets': new_sheets, 
            'in_progress': in_progress, 
            'completed': completed,
            'recent_sheets': recent_sheets
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
        "A0A1": "Điều độ A0/A1",
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
