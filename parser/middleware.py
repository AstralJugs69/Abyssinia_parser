from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import render
import logging
import json

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware:
    """Middleware for comprehensive error handling and user feedback"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        return response
    
    def process_exception(self, request, exception):
        """Handle uncaught exceptions with user-friendly responses"""
        logger.error(f"Uncaught exception: {str(exception)}", exc_info=True)
        
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Format error response based on exception type
        error_response = self._format_exception_response(exception)
        
        if is_ajax:
            return JsonResponse(error_response)
        else:
            # For regular requests, render error page
            return render(request, 'parser/error.html', {
                'error_data': error_response
            }, status=500)
    
    def _format_exception_response(self, exception):
        """Format exception into user-friendly error response"""
        error_msg = str(exception).lower()
        
        # Database connection errors
        if any(term in error_msg for term in ['database', 'connection refused', 'operational error']):
            return {
                'success': False,
                'error': 'Database connection failed',
                'details': 'Could not connect to the database',
                'suggestions': [
                    'Check your internet connection',
                    'Try again in a few minutes',
                    'Contact support if problem persists'
                ],
                'retry_allowed': True
            }
        
        # File system errors
        if any(term in error_msg for term in ['permission denied', 'file not found', 'disk full']):
            return {
                'success': False,
                'error': 'File system error',
                'details': 'Could not access or save files',
                'suggestions': [
                    'Check file permissions',
                    'Ensure sufficient disk space',
                    'Contact administrator'
                ],
                'retry_allowed': True
            }
        
        # Memory errors
        if any(term in error_msg for term in ['memory', 'out of memory']):
            return {
                'success': False,
                'error': 'System resources unavailable',
                'details': 'Not enough memory to complete the operation',
                'suggestions': [
                    'Try processing a smaller file',
                    'Try again later when system load is lower',
                    'Contact administrator'
                ],
                'retry_allowed': True
            }
        
        # Generic server error
        return {
            'success': False,
            'error': 'Server error',
            'details': 'An unexpected server error occurred',
            'suggestions': [
                'Try again in a few minutes',
                'Contact support if problem persists'
            ],
            'retry_allowed': True
        }


class SessionActivityMiddleware:
    """Middleware to track user session activity for cleanup"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Update session activity before processing request
        if hasattr(request, 'session') and request.session.session_key:
            try:
                from .models import UserSession
                UserSession.objects.filter(
                    session_key=request.session.session_key
                ).update(last_activity=timezone.now())
            except Exception as e:
                logger.warning(f"Could not update session activity: {str(e)}")
        
        response = self.get_response(request)
        return response