from django.urls import path
from . import views

urlpatterns = [
    path('', views.sheet_list, name='sheet_list'),
    path('my-sheets/', views.my_sheets, name='my_sheets'),
    path('create/', views.sheet_create, name='sheet_create'),
    path('<int:pk>/', views.sheet_detail, name='sheet_detail'),
    path('<int:pk>/update-status/', views.sheet_update_status, name='sheet_update_status'),
    path('<int:pk>/assign/', views.sheet_assign, name='sheet_assign'),
    path('<int:pk>/sign/initiate/', views.initiate_signature, name='initiate_signature'),
    path('<int:pk>/sign/confirm/', views.confirm_signature, name='confirm_signature'),
    path('<int:pk>/run-mock-ocr/', views.run_mock_ocr, name='run_mock_ocr'),
    path('<int:pk>/save-actual-data/', views.sheet_save_actual_data, name='sheet_save_actual_data'),
]
