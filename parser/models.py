from django.db import models
from django.utils import timezone


class UserSession(models.Model):
    """Model to track user sessions and manage cleanup"""
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Session {self.session_key[:8]}... - {'Active' if self.is_active else 'Inactive'}"
    
    @classmethod
    def get_active_session_count(cls):
        """Get count of currently active sessions"""
        return cls.objects.filter(is_active=True).count()
    
    def deactivate(self):
        """Deactivate this session"""
        self.is_active = False
        self.save()


class ProcessedDocument(models.Model):
    """Model to store processing results and file information"""
    FILE_TYPE_CHOICES = [
        ('jpg', 'JPG Image'),
        ('png', 'PNG Image'),
        ('pdf', 'PDF Document'),
        ('txt', 'Text File'),
    ]
    
    session = models.ForeignKey(UserSession, on_delete=models.CASCADE, related_name='documents')
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    extracted_data = models.JSONField(default=dict, help_text="Structured data extracted from document")
    processing_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    # Storage path of the originally uploaded file (e.g., Supabase key)
    source_file_path = models.CharField(max_length=500, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    error_details = models.JSONField(default=dict, help_text="Detailed error information for debugging")
    retry_count = models.PositiveIntegerField(default=0, help_text="Number of retry attempts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # File paths for generated outputs
    excel_file_path = models.CharField(max_length=500, blank=True, null=True)
    pdf_file_path = models.CharField(max_length=500, blank=True, null=True)
    doc_file_path = models.CharField(max_length=500, blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.filename} - {self.get_processing_status_display()}"
    
    @property
    def is_processing_complete(self):
        """Check if document processing is complete"""
        return self.processing_status == 'completed'
    
    @property
    def has_output_files(self):
        """Check if output files have been generated"""
        return all([self.excel_file_path, self.pdf_file_path, self.doc_file_path])
    
    @property
    def can_retry(self):
        """Check if document processing can be retried"""
        return self.processing_status == 'failed' and self.retry_count < 3
    
    def increment_retry_count(self):
        """Increment retry count and save"""
        self.retry_count += 1
        self.save(update_fields=['retry_count'])
    
    def set_error(self, error_message, error_details=None):
        """Set error information for the document"""
        self.processing_status = 'failed'
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        self.save()
