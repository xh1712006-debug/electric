from django.urls import path
from . import views
from . import views_bulk

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
    path('<int:pk>/update-metadata/', views.sheet_update_metadata, name='sheet_update_metadata'),
    path('ocr-progress/', views.ocr_job_list, name='ocr_job_list'),
    path('ocr-job/<int:pk>/json/', views.ocr_job_json, name='ocr_job_json'),
    path('ocr-job/<int:pk>/retry/', views.ocr_job_retry, name='ocr_job_retry'),
    path('ocr-job/retry-all/', views.ocr_job_retry_all, name='ocr_job_retry_all'),
    path('<int:pk>/route-to-station/', views.sheet_route_to_station, name='sheet_route_to_station'),
    path('updated/', views.updated_sheets, name='updated_sheets'),
    
    # Bulk create (Test Utility)
    path('bulk-create/', views_bulk.bulk_create_ui, name='bulk_create_ui'),
    path('bulk-create/execute/', views_bulk.bulk_create_execute, name='bulk_create_execute'),
    
    # API Extract (Test Utility)
    path('api-extract-test/', views_bulk.api_extract_test_ui, name='api_extract_test_ui'),
    path('api-extract-test/execute/', views_bulk.api_extract_test_execute, name='api_extract_test_execute'),
]
