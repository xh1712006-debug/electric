from django.urls import path
from . import views

urlpatterns = [
    path('', views.station_list, name='station_list'),
    path('create/', views.station_create, name='station_create'),
    path('<int:station_id>/bays/create/', views.bay_create, name='bay_create'),
    path('bays/<int:bay_id>/relays/create/', views.relay_create, name='relay_create'),
    path('bays/<int:bay_id>/relays/bulk_create/', views.relay_bulk_create, name='relay_bulk_create'),
    path('global_bulk_create/', views.global_bulk_create, name='global_bulk_create'),
    path('relay-status/', views.relay_status_dashboard, name='relay_status'),
    path('htmx/station/<int:station_id>/bays/', views.get_bays_htmx, name='htmx_bays'),
    path('htmx/bay/<int:bay_id>/relays/', views.get_relays_htmx, name='htmx_relays'),
    path('relay/<int:relay_id>/autocheck/', views.run_autocheck_now, name='run_autocheck_now'),
    path('relay/<int:relay_id>/update_schedule/', views.update_relay_schedule, name='update_relay_schedule'),
    path('autochecks/', views.autocheck_dashboard, name='autocheck_dashboard'),
    path('htmx/search-suggestions/', views.search_suggestions, name='search_suggestions'),
]
