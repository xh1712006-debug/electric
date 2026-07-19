from django.urls import path
from . import views

urlpatterns = [
    path('', views.check_list, name='check_list'),
    path('new/', views.check_create, name='check_create'),
    path('<int:pk>/', views.check_detail, name='check_detail'),
    path('<int:pk>/items/', views.check_update_item, name='check_update_item'),
    path('<int:pk>/complete/', views.check_complete, name='check_complete'),
]
