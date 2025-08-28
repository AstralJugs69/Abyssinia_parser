from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.views import View
import json
import logging
import io

from .forms import DocumentUploadForm
from .services import SupabaseStorageService, SessionService, OCRService
from .models import ProcessedDocument

logger = logging.getLogger(__name__)


class DocumentUploadView(View):
    """Main view for document upload and processing"""
    
    def get(self, request):
        """Display the upload form"""
        form = DocumentUploadForm()
        
        # Get or create session
        user_session, created, error = SessionService.get_or_create_session(request)
        
        if error:
            messages.error(request, error)
            return render(request, 'parser/upload.html', {
                'form': form,
                'session_error': error
            })
        
        # Get user's processed documents
        documents = ProcessedDocument.objects.filter(session=user_session).order_by('-created_at')
        
        context = {
            'form': form,
            'documents': documents,
            'session_created': created,
            'active_sessions': user_session.get_active_session_count() if user_session else 0
        }
        
        return render(request, 'parser/upload.html', context)
    
    def post(self, request):
        """Handle file upload"""
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get or create session
        user_session, created, error = SessionService.get_or_create_session(request)
        
        if error:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': error
                })
            messages.error(request, error)
            return redirect('upload')
        
        form = DocumentUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                uploaded_file = form.cleaned_data['file']
                file_type = form.get_file_type()
                
                # Upload to Supabase Storage
                storage_service = SupabaseStorageService()
                upload_result = storage_service.upload_file(uploaded_file, user_session.session_key)
                
                if upload_result['success']:
                    # Create ProcessedDocument record
                    document = ProcessedDocument.objects.create(
                        session=user_session,
                        filename=uploaded_file.name,
                        file_type=file_type,
                        file_size=uploaded_file.size,
                        processing_status='pending'
                    )
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': 'File uploaded successfully',
                            'document_id': document.id,
                            'filename': document.filename,
                            'file_type': document.file_type,
                            'file_size': document.file_size
                        })
                    
                    messages.success(request, f'File "{uploaded_file.name}" uploaded successfully!')
                    return redirect('upload')
                
                else:
                    error_msg = upload_result.get('error', 'Upload failed')
                    if is_ajax:
                        return JsonResponse({
                            'success': False,
                            'error': error_msg
                        })
                    messages.error(request, error_msg)
                    
            except Exception as e:
                logger.error(f"Error processing upload: {str(e)}")
                error_msg = 'An error occurred while processing your file'
                
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'error': error_msg
                    })
                messages.error(request, error_msg)
        
        else:
            # Form validation errors
            errors = []
            for field, field_errors in form.errors.items():
                errors.extend(field_errors)
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': '; '.join(errors)
                })
            
            for error in errors:
                messages.error(request, error)
        
        return redirect('upload')


@require_http_methods(["POST"])
@csrf_exempt
def upload_ajax(request):
    """AJAX endpoint for file upload with drag-and-drop support"""
    try:
        # Get or create session
        user_session, created, error = SessionService.get_or_create_session(request)
        
        if error:
            return JsonResponse({
                'success': False,
                'error': error
            })
        
        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'No file provided'
            })
        
        form = DocumentUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            uploaded_file = form.cleaned_data['file']
            file_type = form.get_file_type()
            
            # Upload to Supabase Storage
            storage_service = SupabaseStorageService()
            upload_result = storage_service.upload_file(uploaded_file, user_session.session_key)
            
            if upload_result['success']:
                # Create ProcessedDocument record
                document = ProcessedDocument.objects.create(
                    session=user_session,
                    filename=uploaded_file.name,
                    file_type=file_type,
                    file_size=uploaded_file.size,
                    processing_status='pending'
                )
                
                return JsonResponse({
                    'success': True,
                    'message': 'File uploaded successfully',
                    'document_id': document.id,
                    'filename': document.filename,
                    'file_type': document.file_type,
                    'file_size': f"{document.file_size / (1024*1024):.1f}MB"
                })
            
            else:
                return JsonResponse({
                    'success': False,
                    'error': upload_result.get('error', 'Upload failed')
                })
        
        else:
            errors = []
            for field, field_errors in form.errors.items():
                errors.extend(field_errors)
            
            return JsonResponse({
                'success': False,
                'error': '; '.join(errors)
            })
    
    except Exception as e:
        logger.error(f"Error in AJAX upload: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while processing your file'
        })


@require_http_methods(["POST"])
@csrf_exempt
def process_document(request):
    """Process uploaded document with comprehensive error handling and user feedback"""
    document = None
    
    try:
        # Get document ID from request
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid request format',
                'details': 'Request body must be valid JSON',
                'suggestions': ['Check your request format and try again'],
                'retry_allowed': True
            })
        
        document_id = data.get('document_id')
        
        if not document_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing document ID',
                'details': 'Document ID is required to process the file',
                'suggestions': ['Make sure you uploaded a file first'],
                'retry_allowed': False
            })
        
        # Get or create session
        user_session, created, error = SessionService.get_or_create_session(request)
        
        if error:
            return JsonResponse({
                'success': False,
                'error': 'Session error',
                'details': error,
                'suggestions': ['Try refreshing the page', 'Clear your browser cache'],
                'retry_allowed': True
            })
        
        # Get the document
        try:
            document = ProcessedDocument.objects.get(
                id=document_id,
                session=user_session
            )
        except ProcessedDocument.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Document not found',
                'details': 'The requested document could not be found in your session',
                'suggestions': ['Try uploading the file again', 'Check that you are using the correct session'],
                'retry_allowed': True
            })
        
        # Check if document is already being processed
        if document.processing_status == 'processing':
            return JsonResponse({
                'success': False,
                'error': 'Document already being processed',
                'details': 'This document is currently being processed',
                'suggestions': ['Please wait for the current processing to complete'],
                'retry_allowed': False
            })
        
        # Check if document was already processed successfully
        if document.processing_status == 'completed':
            return JsonResponse({
                'success': True,
                'message': 'Document already processed',
                'data': {
                    'text': document.extracted_data.get('text', ''),
                    'confidence': document.extracted_data.get('confidence', 0),
                    'word_count': document.extracted_data.get('word_count', 0),
                    'document_id': document.id
                }
            })
        
        # Update status to processing
        document.processing_status = 'processing'
        document.error_message = None  # Clear any previous errors
        document.save()
        
        # Get file from storage
        storage_service = SupabaseStorageService()
        file_path = f"{user_session.session_key}/{document.filename}"
        
        try:
            file_content = storage_service.get_file_content(file_path)
        except Exception as storage_error:
            document.processing_status = 'failed'
            document.error_message = f'Storage error: {str(storage_error)}'
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'File retrieval failed',
                'details': 'Could not retrieve the uploaded file from storage',
                'suggestions': [
                    'Try uploading the file again',
                    'Check your internet connection',
                    'Contact support if problem persists'
                ],
                'retry_allowed': True
            })
        
        if not file_content:
            document.processing_status = 'failed'
            document.error_message = 'File content is empty or could not be retrieved'
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'Empty file',
                'details': 'The uploaded file appears to be empty or corrupted',
                'suggestions': [
                    'Check that your original file contains data',
                    'Try uploading the file again',
                    'Try uploading a different file'
                ],
                'retry_allowed': True
            })
        
        # Process with OCR
        ocr_service = OCRService()
        
        # Create file-like object from content
        file_obj = io.BytesIO(file_content)
        
        # Process based on file type with progress tracking
        try:
            result = ocr_service.process_file(file_obj, document.file_type)
        except Exception as processing_error:
            document.processing_status = 'failed'
            document.error_message = f'Processing error: {str(processing_error)}'
            document.save()
            
            # Use ErrorHandler for consistent error formatting
            from .services import ErrorHandler
            error_response = ErrorHandler.get_user_friendly_error(processing_error)
            return JsonResponse(error_response)
        
        if result['success']:
            # Update document with results
            document.extracted_data = {
                'text': result['text'],
                'confidence': result['confidence'],
                'word_count': result['word_count'],
                'processing_method': 'OCR' if document.file_type in ['jpg', 'jpeg', 'png', 'pdf'] else 'Direct',
                'processed_at': datetime.now().isoformat()
            }
            document.processing_status = 'completed'
            document.error_message = None
            document.save()
            
            return JsonResponse({
                'success': True,
                'message': result['message'],
                'data': {
                    'text': result['text'],
                    'confidence': result['confidence'],
                    'word_count': result['word_count'],
                    'document_id': document.id,
                    'processing_method': document.extracted_data['processing_method']
                }
            })
        
        else:
            # Update document with detailed error information
            document.set_error(
                error_message=result.get('error', 'Unknown error'),
                error_details={
                    'details': result.get('details'),
                    'suggestions': result.get('suggestions', []),
                    'fallback_suggestion': result.get('fallback_suggestion'),
                    'retry_allowed': result.get('retry_allowed', True),
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            # Return detailed error information
            error_response = {
                'success': False,
                'error': result.get('error', 'Processing failed'),
                'retry_allowed': result.get('retry_allowed', True)
            }
            
            # Add optional fields if they exist
            for field in ['details', 'suggestions', 'fallback_suggestion', 'installation_help']:
                if field in result:
                    error_response[field] = result[field]
            
            return JsonResponse(error_response)
    
    except Exception as e:
        logger.error(f"Unexpected error processing document: {str(e)}")
        
        # Update document status if we have it
        if document:
            document.processing_status = 'failed'
            document.error_message = f'Unexpected error: {str(e)}'
            document.save()
        
        # Use ErrorHandler for consistent error formatting
        from .services import ErrorHandler
        error_response = ErrorHandler.get_user_friendly_error(e)
        return JsonResponse(error_response)


@require_http_methods(["POST"])
@csrf_exempt
def retry_document_processing(request):
    """Retry processing a failed document"""
    try:
        # Get document ID from request
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid request format',
                'details': 'Request body must be valid JSON'
            })
        
        document_id = data.get('document_id')
        
        if not document_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing document ID'
            })
        
        # Get or create session
        user_session, created, error = SessionService.get_or_create_session(request)
        
        if error:
            return JsonResponse({
                'success': False,
                'error': error
            })
        
        # Get the document
        try:
            document = ProcessedDocument.objects.get(
                id=document_id,
                session=user_session
            )
        except ProcessedDocument.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Document not found'
            })
        
        # Check if document can be retried
        if not document.can_retry:
            if document.retry_count >= 3:
                return JsonResponse({
                    'success': False,
                    'error': 'Maximum retry attempts reached',
                    'details': f'Document has been retried {document.retry_count} times',
                    'suggestions': [
                        'Try uploading the file again',
                        'Check that your file is not corrupted',
                        'Contact support if problem persists'
                    ],
                    'retry_allowed': False
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Document cannot be retried',
                    'details': f'Document status is {document.processing_status}',
                    'retry_allowed': False
                })
        
        # Reset document status for retry and increment retry count
        document.processing_status = 'pending'
        document.error_message = None
        document.error_details = {}
        document.increment_retry_count()
        document.save()
        
        # Call the regular processing function
        # Create a new request object with the document ID
        retry_request = type('Request', (), {
            'body': json.dumps({'document_id': document_id}).encode(),
            'session': request.session,
            'headers': request.headers
        })()
        
        return process_document(retry_request)
        
    except Exception as e:
        logger.error(f"Error retrying document processing: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Retry failed',
            'details': str(e)
        })


@require_http_methods(["GET"])
def get_processing_status(request, document_id):
    """Get current processing status of a document"""
    try:
        # Get or create session
        user_session, created, error = SessionService.get_or_create_session(request)
        
        if error:
            return JsonResponse({
                'success': False,
                'error': error
            })
        
        # Get the document
        try:
            document = ProcessedDocument.objects.get(
                id=document_id,
                session=user_session
            )
        except ProcessedDocument.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Document not found'
            })
        
        response_data = {
            'success': True,
            'document_id': document.id,
            'filename': document.filename,
            'status': document.processing_status,
            'created_at': document.created_at.isoformat(),
            'updated_at': document.updated_at.isoformat()
        }
        
        # Add error information if failed
        if document.processing_status == 'failed' and document.error_message:
            response_data['error_message'] = document.error_message
        
        # Add extracted data if completed
        if document.processing_status == 'completed' and document.extracted_data:
            response_data['extracted_data'] = {
                'word_count': document.extracted_data.get('word_count', 0),
                'confidence': document.extracted_data.get('confidence', 0),
                'processing_method': document.extracted_data.get('processing_method', 'Unknown')
            }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error getting processing status: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Could not get processing status',
            'details': str(e)
        })
