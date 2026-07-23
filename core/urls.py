from django.urls import path
from . import views

urlpatterns = [
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/update/', views.user_update, name='user_update'),
    path('users/<int:user_id>/toggle-status/', views.user_toggle_status, name='user_toggle_status'),
    path('roles/', views.role_matrix, name='role_matrix'),
    path('roles/update/', views.role_matrix_update, name='role_matrix_update'),
    path('dispatcher/routed-relays/', views.dispatcher_routed_relays, name='dispatcher_routed_relays'),
    path('profile/', views.profile, name='profile'),
]
