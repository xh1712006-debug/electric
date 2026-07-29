from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'management-units', views.ManagementUnitViewSet)
router.register(r'manufacturing-countries', views.ManufacturingCountryViewSet)
router.register(r'manufacturers', views.ManufacturerViewSet)
router.register(r'ownerships', views.OwnershipViewSet)
router.register(r'voltage-levels', views.VoltageLevelViewSet)
router.register(r'equipment-types', views.EquipmentTypeViewSet)
router.register(r'operational-statuses', views.OperationalStatusViewSet)
router.register(r'lines', views.LineViewSet)
router.register(r'projects', views.ProjectViewSet)
router.register(r'locations', views.LocationViewSet)

# Include existing stations app categories for consistency in the API namespace
router.register(r'stations', views.StationViewSet)
router.register(r'bays', views.BayViewSet)
router.register(r'equipments', views.RelayViewSet) # Exposing Relay as equipment

urlpatterns = [
    # UI endpoints
    path('dashboard/', views.category_dashboard, name='category_dashboard'),
    path('ui/<str:category_id>/', views.category_list, name='category_list'),
    path('ui/<str:category_id>/new/', views.category_form, name='category_create'),
    path('ui/<str:category_id>/<int:pk>/edit/', views.category_form, name='category_edit'),
    path('ui/<str:category_id>/<int:pk>/delete/', views.category_delete, name='category_delete'),
    
    # Asset Management UI
    path('assets/lines/', views.asset_line_list, name='asset_line_list'),
    path('assets/locations/', views.asset_location_list, name='asset_location_list'),
    path('assets/projects/', views.asset_project_list, name='asset_project_list'),
    
    # API endpoints
    path('', include(router.urls)),
]
