from django.urls import path
from . import views

urlpatterns = [
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('roles/', views.role_matrix, name='role_matrix'),
    path('roles/update/', views.role_matrix_update, name='role_matrix_update'),
]
