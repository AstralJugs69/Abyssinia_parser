from django.urls import path
from . import views

urlpatterns = [
    path('', views.DocumentUploadView.as_view(), name='upload'),
    path('upload-ajax/', views.upload_ajax, name='upload_ajax'),
    path('process-document/', views.process_document, name='process_document'),
    path('retry-processing/', views.retry_document_processing, name='retry_processing'),
    path('status/<int:document_id>/', views.get_processing_status, name='processing_status'),
]