from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload, name='upload'),
    path('process/', views.process, name='process'),
    # Async API endpoints for upload, processing, status, and download
    path('api/upload/', views.upload_ajax, name='upload_ajax'),
    path('api/process/', views.process_document, name='process_document'),
    path('api/status/<int:document_id>/', views.get_processing_status, name='get_processing_status'),
    path('api/retry/', views.retry_document_processing, name='retry_document_processing'),
    # Diagnostics and health endpoints
    path('api/health/', views.health_check, name='health_check'),
    path('api/test/ocr/<int:document_id>/', views.test_ocr_only, name='test_ocr_only'),
    path('api/test/llm/', views.test_llm_only, name='test_llm_only'),
    path('download/<int:document_id>/<str:file_type>/', views.download_file, name='download_file'),
]