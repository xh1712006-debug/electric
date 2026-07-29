from rest_framework import viewsets
from .models import (
    ManagementUnit, ManufacturingCountry, Manufacturer, Ownership,
    VoltageLevel, EquipmentType, OperationalStatus, Line, Project, Location
)
from stations.models import Station, Bay, Relay
from .serializers import (
    ManagementUnitSerializer, ManufacturingCountrySerializer, ManufacturerSerializer, OwnershipSerializer,
    VoltageLevelSerializer, EquipmentTypeSerializer, OperationalStatusSerializer, LineSerializer, ProjectSerializer, LocationSerializer,
    StationSerializer, BaySerializer, RelaySerializer
)

class CategoryBaseViewSet(viewsets.ModelViewSet):
    # Base class can hold common logic if needed
    pass

class ManagementUnitViewSet(CategoryBaseViewSet):
    queryset = ManagementUnit.objects.all()
    serializer_class = ManagementUnitSerializer

class ManufacturingCountryViewSet(CategoryBaseViewSet):
    queryset = ManufacturingCountry.objects.all()
    serializer_class = ManufacturingCountrySerializer

class ManufacturerViewSet(CategoryBaseViewSet):
    queryset = Manufacturer.objects.all()
    serializer_class = ManufacturerSerializer

class OwnershipViewSet(CategoryBaseViewSet):
    queryset = Ownership.objects.all()
    serializer_class = OwnershipSerializer

class VoltageLevelViewSet(CategoryBaseViewSet):
    queryset = VoltageLevel.objects.all()
    serializer_class = VoltageLevelSerializer

class EquipmentTypeViewSet(CategoryBaseViewSet):
    queryset = EquipmentType.objects.all()
    serializer_class = EquipmentTypeSerializer

class OperationalStatusViewSet(CategoryBaseViewSet):
    queryset = OperationalStatus.objects.all()
    serializer_class = OperationalStatusSerializer

class LineViewSet(CategoryBaseViewSet):
    queryset = Line.objects.all()
    serializer_class = LineSerializer

class ProjectViewSet(CategoryBaseViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

class LocationViewSet(CategoryBaseViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer

class StationViewSet(viewsets.ModelViewSet):
    queryset = Station.objects.all()
    serializer_class = StationSerializer

class BayViewSet(viewsets.ModelViewSet):
    queryset = Bay.objects.all()
    serializer_class = BaySerializer

class RelayViewSet(viewsets.ModelViewSet):
    queryset = Relay.objects.all()
    serializer_class = RelaySerializer


# ==========================================
# UI Views for HTMX + TailwindCSS
# ==========================================
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404
from django.core.paginator import Paginator
from django import forms
import importlib

# Map category ID to model class
CATEGORY_MODELS = {
    'management_unit': ('categories.models', 'ManagementUnit', 'Đơn vị quản lý'),
    'manufacturing_country': ('categories.models', 'ManufacturingCountry', 'Nước sản xuất'),
    'manufacturer': ('categories.models', 'Manufacturer', 'Hãng sản xuất'),
    'ownership': ('categories.models', 'Ownership', 'Sở hữu'),
    'voltage_level': ('categories.models', 'VoltageLevel', 'Cấp điện áp'),
    'equipment_type': ('categories.models', 'EquipmentType', 'Loại thiết bị'),
    'operational_status': ('categories.models', 'OperationalStatus', 'Trạng thái vận hành'),
    'line': ('categories.models', 'Line', 'Đường dây'),
    'project': ('categories.models', 'Project', 'Công trình'),
    'location': ('categories.models', 'Location', 'Vị trí'),
    'station': ('stations.models', 'Station', 'Trạm'),
    'bay': ('stations.models', 'Bay', 'Ngăn lộ'),
    'relay': ('stations.models', 'Relay', 'Thiết bị (Rơ-le)'),
}

def get_model_class(category_id):
    if category_id not in CATEGORY_MODELS:
        raise Http404("Category not found")
    module_name, class_name, _ = CATEGORY_MODELS[category_id]
    module = importlib.import_module(module_name)
    return getattr(module, class_name)

def get_category_form(model_class):
    class DynamicCategoryForm(forms.ModelForm):
        class Meta:
            model = model_class
            exclude = ['created_at', 'updated_at']
            
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for field_name, field in self.fields.items():
                widget = field.widget
                attrs = widget.attrs
                attrs['class'] = 'w-full px-3 py-2 border border-slate-300 rounded-lg shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none text-sm text-slate-800 bg-white transition-colors'
                if isinstance(widget, forms.Textarea):
                    attrs['rows'] = 3
                
    return DynamicCategoryForm

@login_required
def category_dashboard(request):
    categories = [{'id': k, 'name': v[2], 'api': k.replace('_', '-')} for k, v in CATEGORY_MODELS.items()]
    return render(request, 'categories/category_dashboard.html', {'categories': categories})

@login_required
def category_list(request, category_id):
    model_class = get_model_class(category_id)
    _, _, name = CATEGORY_MODELS[category_id]
    
    queryset = model_class.objects.all().order_by('-id')
    
    query = request.GET.get('q', '')
    if query:
        if category_id == 'station':
            queryset = queryset.filter(station_name__icontains=query) | queryset.filter(station_code__icontains=query)
        elif category_id == 'bay':
            queryset = queryset.filter(bay_name__icontains=query) | queryset.filter(bay_code__icontains=query)
        elif category_id == 'relay':
            queryset = queryset.filter(relay_name__icontains=query) | queryset.filter(relay_code__icontains=query)
        else:
            queryset = queryset.filter(name__icontains=query) | queryset.filter(code__icontains=query)

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'category_id': category_id,
        'category_name': name,
        'q': query
    }

    if request.headers.get('HX-Request'):
        return render(request, 'categories/partials/category_list_partial.html', context)
    return render(request, 'categories/category_list.html', context)

@login_required
def category_form(request, category_id, pk=None):
    model_class = get_model_class(category_id)
    _, _, name = CATEGORY_MODELS[category_id]
    FormClass = get_category_form(model_class)
    
    instance = get_object_or_404(model_class, pk=pk) if pk else None

    if request.method == 'POST':
        form = FormClass(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={'HX-Trigger': 'categoryListChanged'})
    else:
        form = FormClass(instance=instance)

    return render(request, 'categories/partials/category_form_modal.html', {
        'form': form,
        'category_id': category_id,
        'category_name': name,
        'instance': instance
    })

@login_required
def category_delete(request, category_id, pk):
    model_class = get_model_class(category_id)
    instance = get_object_or_404(model_class, pk=pk)
    if request.method == 'POST':
        instance.delete()
        return HttpResponse(status=204, headers={'HX-Trigger': 'categoryListChanged'})
    return HttpResponse(status=400)


# ==========================================
# Asset Management Views (Advanced List + Slide-over)
# ==========================================

@login_required
def asset_line_list(request):
    """Danh sách Đường dây với Advanced Table + Slide-over"""
    from .models import Line, VoltageLevel, OperationalStatus
    queryset = Line.objects.all().order_by('code')
    
    q = request.GET.get('q', '')
    filter_capda = request.GET.get('capda', '')
    filter_ttvh = request.GET.get('ttvh', '')
    
    if q:
        queryset = queryset.filter(name__icontains=q) | queryset.filter(code__icontains=q)
    if filter_capda:
        vl = VoltageLevel.objects.filter(code=filter_capda).first()
        capda_val = vl.legacy_code if (vl and vl.legacy_code) else filter_capda
        queryset = queryset.filter(id_capda=capda_val)
    if filter_ttvh:
        queryset = queryset.filter(id_ttvh=filter_ttvh)
    
    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    # Detail view for slide-over
    detail_pk = request.GET.get('detail')
    detail_obj = Line.objects.filter(pk=detail_pk).first() if detail_pk else None
    
    context = {
        'page_obj': page_obj,
        'q': q,
        'filter_capda': filter_capda,
        'filter_ttvh': filter_ttvh,
        'voltage_levels': VoltageLevel.objects.all().order_by('code'),
        'op_statuses': OperationalStatus.objects.all().order_by('code'),
        'detail_obj': detail_obj,
        'total_count': queryset.count(),
    }
    if request.GET.get('_panel') == '1':
        return render(request, 'categories/partials/line_detail_panel.html', {'obj': detail_obj})
    return render(request, 'categories/asset_line_list.html', context)


@login_required
def asset_location_list(request):
    """Danh sách Vị trí / Cột điện với Advanced Table + Slide-over"""
    from .models import Location, VoltageLevel, OperationalStatus
    queryset = Location.objects.all().order_by('code')
    
    q = request.GET.get('q', '')
    filter_capda = request.GET.get('capda', '')
    filter_ttvh = request.GET.get('ttvh', '')
    
    if q:
        queryset = queryset.filter(name__icontains=q) | queryset.filter(code__icontains=q)
    if filter_capda:
        vl = VoltageLevel.objects.filter(code=filter_capda).first()
        capda_val = vl.legacy_code if (vl and vl.legacy_code) else filter_capda
        queryset = queryset.filter(id_capda=capda_val)
    if filter_ttvh:
        queryset = queryset.filter(id_ttvh=filter_ttvh)
    
    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    detail_pk = request.GET.get('detail')
    detail_obj = Location.objects.filter(pk=detail_pk).first() if detail_pk else None
    
    context = {
        'page_obj': page_obj,
        'q': q,
        'filter_capda': filter_capda,
        'filter_ttvh': filter_ttvh,
        'voltage_levels': VoltageLevel.objects.all().order_by('code'),
        'op_statuses': OperationalStatus.objects.all().order_by('code'),
        'detail_obj': detail_obj,
        'total_count': queryset.count(),
    }
    if request.GET.get('_panel') == '1':
        return render(request, 'categories/partials/location_detail_panel.html', {'obj': detail_obj})
    return render(request, 'categories/asset_location_list.html', context)


@login_required
def asset_project_list(request):
    """Danh sách Công trình với Advanced Table + Slide-over"""
    from .models import Project, VoltageLevel, OperationalStatus
    queryset = Project.objects.all().order_by('code')
    
    q = request.GET.get('q', '')
    filter_capda = request.GET.get('capda', '')
    filter_ttvh = request.GET.get('ttvh', '')
    
    if q:
        queryset = queryset.filter(name__icontains=q) | queryset.filter(code__icontains=q)
    if filter_capda:
        vl = VoltageLevel.objects.filter(code=filter_capda).first()
        capda_val = vl.legacy_code if (vl and vl.legacy_code) else filter_capda
        queryset = queryset.filter(id_capda=capda_val)
    if filter_ttvh:
        queryset = queryset.filter(id_ttvh=filter_ttvh)
    
    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    detail_pk = request.GET.get('detail')
    detail_obj = Project.objects.filter(pk=detail_pk).first() if detail_pk else None
    
    context = {
        'page_obj': page_obj,
        'q': q,
        'filter_capda': filter_capda,
        'filter_ttvh': filter_ttvh,
        'voltage_levels': VoltageLevel.objects.all().order_by('code'),
        'op_statuses': OperationalStatus.objects.all().order_by('code'),
        'detail_obj': detail_obj,
        'total_count': queryset.count(),
    }
    if request.GET.get('_panel') == '1':
        return render(request, 'categories/partials/project_detail_panel.html', {'obj': detail_obj})
    return render(request, 'categories/asset_project_list.html', context)
