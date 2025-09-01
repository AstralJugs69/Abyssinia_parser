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
import os
from datetime import datetime

from .forms import DocumentUploadForm
# Removed legacy imports of services/models to avoid heavy optional deps

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
                'retry_allowed': True
            })
        
        document_id = data.get('document_id')
        
        if not document_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing document ID',
                'retry_allowed': False
            })
        
        # Get or create session
        user_session, created, error = SessionService.get_or_create_session(request)
        
        if error:
            return JsonResponse({
                'success': False,
                'error': error,
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
                'retry_allowed': True
            })
        
        # Check if document is already being processed
        if document.processing_status == 'processing':
            return JsonResponse({
                'success': False,
                'error': 'Document already being processed',
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
                'retry_allowed': True
            })
        
        if not file_content:
            document.processing_status = 'failed'
            document.error_message = 'File content is empty or could not be retrieved'
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'Empty file',
                'retry_allowed': True
            })
        
        # Complete processing workflow: OCR -> LLM -> Data Structuring -> File Generation
        from .services import OCRService, LLMService, DataStructuringService, FileGenerationService
        from datetime import datetime
        
        # Step 1: Extract text with OCR (for images/PDFs) or direct reading (for text files)
        ocr_service = OCRService()
        file_obj = io.BytesIO(file_content)
        
        try:
            ocr_result = ocr_service.process_file(file_obj, document.file_type)
        except Exception as processing_error:
            document.processing_status = 'failed'
            document.error_message = f'Text extraction error: {str(processing_error)}'
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'Text extraction failed',
                'retry_allowed': True
            })
        
        if not ocr_result['success']:
            document.processing_status = 'failed'
            document.error_message = ocr_result.get('error', 'Text extraction failed')
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': ocr_result.get('error', 'Text extraction failed'),
                'retry_allowed': ocr_result.get('retry_allowed', True)
            })
        
        extracted_text = ocr_result['data']['text']
        
        # Step 2: Parse extracted text with LLM
        llm_service = LLMService()
        
        try:
            llm_result = llm_service.parse_banking_document(extracted_text)
        except Exception as llm_error:
            document.processing_status = 'failed'
            document.error_message = f'LLM parsing error: {str(llm_error)}'
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'Document parsing failed',
                'retry_allowed': True
            })
        
        if not llm_result['success']:
            document.processing_status = 'failed'
            document.error_message = llm_result.get('error', 'LLM parsing failed')
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': llm_result.get('error', 'Document parsing failed'),
                'retry_allowed': llm_result.get('retry_allowed', True)
            })
        
        parsed_data = llm_result['data']
        
        # Step 3: Structure the data
        structuring_service = DataStructuringService()
        
        try:
            structured_result = structuring_service.structure_banking_data(parsed_data)
        except Exception as structuring_error:
            document.processing_status = 'failed'
            document.error_message = f'Data structuring error: {str(structuring_error)}'
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'Data structuring failed',
                'retry_allowed': True
            })
        
        if not structured_result['success']:
            document.processing_status = 'failed'
            document.error_message = structured_result.get('error', 'Data structuring failed')
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': structured_result.get('error', 'Data structuring failed'),
                'retry_allowed': structured_result.get('retry_allowed', True)
            })
        
        structured_data = structured_result['data']
        
        # Step 4: Generate output files
        file_generation_service = FileGenerationService()
        
        try:
            generation_result = file_generation_service.generate_all_formats(
                structured_data, 
                user_session.session_key
            )
        except Exception as generation_error:
            document.processing_status = 'failed'
            document.error_message = f'File generation error: {str(generation_error)}'
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'File generation failed',
                'retry_allowed': True
            })
        
        if not generation_result['success']:
            document.processing_status = 'failed'
            document.error_message = generation_result.get('error', 'File generation failed')
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': generation_result.get('error', 'File generation failed'),
                'retry_allowed': generation_result.get('retry_allowed', True)
            })
        
        # Step 5: Upload generated files to Supabase Storage
        storage_service = SupabaseStorageService()
        uploaded_files = {}
        
        for file_type, file_info in generation_result['files'].items():
            try:
                local_path = file_info['path']
                if os.path.exists(local_path):
                    # Read the generated file
                    with open(local_path, 'rb') as f:
                        file_content = f.read()
                    
                    # Create a file-like object for upload
                    from django.core.files.uploadedfile import SimpleUploadedFile
                    uploaded_file = SimpleUploadedFile(
                        name=file_info['filename'],
                        content=file_content,
                        content_type={
                            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            'pdf': 'application/pdf',
                            'doc': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                        }.get(file_type, 'application/octet-stream')
                    )
                    
                    # Upload to storage
                    upload_result = storage_service.upload_file(uploaded_file, user_session.session_key)
                    
                    if upload_result['success']:
                        uploaded_files[file_type] = upload_result['file_path']
                    else:
                        logger.warning(f"Failed to upload {file_type} file: {upload_result.get('error')}")
                        uploaded_files[file_type] = local_path  # Fallback to local path
                    
                    # Clean up local file
                    try:
                        os.remove(local_path)
                    except:
                        pass
                        
            except Exception as upload_error:
                logger.error(f"Error uploading {file_type} file: {str(upload_error)}")
                uploaded_files[file_type] = file_info['path']  # Fallback to local path
        
        # Step 6: Update document with complete results
        document.extracted_data = {
            'raw_text': extracted_text,
            'parsed_data': parsed_data,
            'structured_data': structured_data,
            'confidence': 0.8,  # Default confidence for simplified OCR
            'word_count': ocr_result.get('data', {}).get('word_count', 0),
            'processing_method': 'OCR+LLM' if document.file_type in ['jpg', 'jpeg', 'png', 'pdf'] else 'LLM',
            'processed_at': datetime.now().isoformat()
        }
        
        # Store file paths (now in Supabase storage)
        document.excel_file_path = uploaded_files.get('excel')
        document.pdf_file_path = uploaded_files.get('pdf')
        document.doc_file_path = uploaded_files.get('doc')
        
        document.processing_status = 'completed'
        document.error_message = None
        document.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Document processed successfully',
            'data': {
                'text': extracted_text[:500] + '...' if len(extracted_text) > 500 else extracted_text,
                'structured_data': structured_data,
                'confidence': document.extracted_data['confidence'],
                'word_count': document.extracted_data['word_count'],
                'document_id': document.id,
                'processing_method': document.extracted_data['processing_method'],
                'files_generated': True
            }
        })
    
    except Exception as e:
        logger.error(f"Unexpected error processing document: {str(e)}")
        
        # Update document status if we have it
        if document:
            document.processing_status = 'failed'
            document.error_message = f'Unexpected error: {str(e)}'
            document.save()
        
        return JsonResponse({
            'success': False,
            'error': 'Processing failed',
            'retry_allowed': True
        })


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
                'error': 'Invalid request format'
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
                    'retry_allowed': False
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Document cannot be retried',
                    'retry_allowed': False
                })
        
        # Reset document status for retry and increment retry count
        document.processing_status = 'pending'
        document.error_message = None
        document.retry_count += 1
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
            'error': 'Retry failed'
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
            'error': 'Could not get processing status'
        })


@require_http_methods(["POST"])
@csrf_exempt
def cleanup_session(request):
    """Manually clean up current user session and files"""
    try:
        from .services import FileCleanupService
        
        # Get current session
        user_session, created, error = SessionService.get_or_create_session(request)
        
        if error or not user_session:
            return JsonResponse({
                'success': False,
                'error': 'No active session found'
            })
        
        # Perform cleanup
        cleanup_service = FileCleanupService()
        result = cleanup_service.cleanup_session_manually(
            user_session.session_key
        )
        
        if result.get('success'):
            storage_cleanup = result.get('storage_cleanup', {})
            database_cleanup = result.get('database_cleanup', {})
            
            files_deleted = storage_cleanup.get('files_deleted', 0)
            docs_deleted = database_cleanup.get('documents_deleted', 0)
            
            return JsonResponse({
                'success': True,
                'message': f'Session cleaned up successfully',
                'files_deleted': files_deleted,
                'documents_deleted': docs_deleted
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Cleanup failed'
            })
            
    except Exception as e:
        logger.error(f"Error during session cleanup: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Cleanup operation failed'
        })


@require_http_methods(["GET"])
def get_cleanup_info(request):
    """Get information about files that can be cleaned up"""
    try:
        from .services import FileCleanupService
        
        cleanup_service = FileCleanupService()
        candidates = cleanup_service.get_cleanup_candidates(hours_old=1)
        
        if candidates.get('success'):
            return JsonResponse({
                'success': True,
                'cleanup_candidates': {
                    'old_sessions_count': candidates.get('old_sessions_count', 0),
                    'old_documents_count': candidates.get('old_documents_count', 0),
                    'cleanup_recommended': candidates.get('cleanup_recommended', False)
                },
                'storage_stats': candidates.get('storage_stats', {})
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Could not get cleanup information'
            })
            
    except Exception as e:
        logger.error(f"Error getting cleanup info: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Could not retrieve cleanup information'
        })


@require_http_methods(["GET"])
def get_document_results(request, document_id):
    """Get structured results for a processed document"""
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
        
        # Check if document is processed
        if document.processing_status != 'completed':
            return JsonResponse({
                'success': False,
                'error': 'Document not yet processed',
                'status': document.processing_status
            })
        
        # Get structured data
        structured_data = document.extracted_data.get('structured_data', {})
        
        return JsonResponse({
            'success': True,
            'document_id': document.id,
            'filename': document.filename,
            'results': structured_data,
            'confidence': document.extracted_data.get('confidence', 0),
            'processing_method': document.extracted_data.get('processing_method', 'Unknown'),
            'processed_at': document.extracted_data.get('processed_at'),
            'has_files': document.has_output_files
        })
        
    except Exception as e:
        logger.error(f"Error getting document results: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Could not retrieve document results'
        })


@require_http_methods(["GET"])
def download_file(request, document_id, file_type):
    """Download generated output files"""
    try:
        from django.http import HttpResponse, Http404
        from .services import SupabaseStorageService
        
        # Validate file type
        if file_type not in ['excel', 'pdf', 'doc']:
            raise Http404("Invalid file type")
        
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
            raise Http404("Document not found")
        
        # Check if document is processed
        if document.processing_status != 'completed':
            return JsonResponse({
                'success': False,
                'error': 'Document not yet processed'
            })
        
        # Get file path based on type
        file_path_attr = f'{file_type}_file_path'
        file_path = getattr(document, file_path_attr, None)
        
        if not file_path:
            return JsonResponse({
                'success': False,
                'error': f'{file_type.upper()} file not available'
            })
        
        # Download file from storage
        storage_service = SupabaseStorageService()
        file_content = storage_service.get_file_content(file_path)
        
        if not file_content:
            return JsonResponse({
                'success': False,
                'error': 'File could not be retrieved from storage'
            })
        
        # Set appropriate content type and filename
        content_types = {
            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'pdf': 'application/pdf',
            'doc': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        
        extensions = {
            'excel': '.xlsx',
            'pdf': '.pdf',
            'doc': '.docx'
        }
        
        # Create filename
        base_name = os.path.splitext(document.filename)[0]
        download_filename = f"{base_name}_processed{extensions[file_type]}"
        
        # Create response
        response = HttpResponse(
            file_content,
            content_type=content_types[file_type]
        )
        response['Content-Disposition'] = f'attachment; filename="{download_filename}"'
        
        return response
        
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Could not download file'
        })

# --- Minimal simplified views ---
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
import os
import io
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .forms import DocumentUploadForm
from . import ocr_pipeline as pipeline


@require_http_methods(["GET"])
def upload(request):
    """Render minimal upload form"""
    form = DocumentUploadForm()
    return render(request, 'parser/simple_upload.html', {'form': form})


@require_http_methods(["POST"]) 
def process(request):
    """Process uploaded file and return cleaned Excel"""
    form = DocumentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        # Re-render with errors
        return render(request, 'parser/simple_upload.html', {'form': form}, status=400)

    f = form.cleaned_data['file']
    ext = os.path.splitext(f.name)[1].lower()
    output_format = form.cleaned_data.get('output_format') or 'excel'

    try:
        use_vision = pipeline.should_use_gemini_vision()

        # Read the uploaded file once for consistent reuse
        try:
            f.seek(0)
        except Exception:
            pass
        file_bytes = f.read()

        structured = None
        original_images = []  # For PDF fallback when input is image(s)

        if ext in ['.jpg', '.jpeg', '.png']:
            # Keep original image for PDF fallback
            orig_img = Image.open(io.BytesIO(file_bytes))
            original_images = [orig_img]
            # Preprocess for OCR/LLM
            img = pipeline.preprocess_image(file_bytes)
            if use_vision:
                structured = pipeline.structure_with_gemini_vision([img])
            else:
                text = pipeline.extract_text_from_image(img)
                structured = pipeline.call_gemini_to_structure(text)
        elif ext == '.pdf':
            if use_vision:
                # Extract images from PDF, preprocess, and send to Vision
                images = pipeline.images_from_pdf(io.BytesIO(file_bytes))
                proc_images = []
                for im in images:
                    buf = io.BytesIO()
                    im.save(buf, format='PNG')
                    proc_images.append(pipeline.preprocess_image(buf.getvalue()))
                structured = pipeline.structure_with_gemini_vision(proc_images)
            else:
                text = pipeline.extract_text_from_pdf(io.BytesIO(file_bytes))
                structured = pipeline.call_gemini_to_structure(text)
        else:
            return HttpResponseBadRequest('Unsupported file type')

        base = os.path.splitext(os.path.basename(f.name))[0]

        def _register_unicode_font() -> str:
            """Register a Unicode font and return its name for ReportLab.
            Preference order: PDF_FONT_PATH env -> Noto Sans Ethiopic -> Noto Sans -> Helvetica.
            """
            # 1) User-provided font via env
            env_path = os.getenv("PDF_FONT_PATH")
            env_name = os.getenv("PDF_FONT_NAME", "CustomPDFUnicode")
            if env_path:
                try:
                    if os.path.exists(env_path):
                        pdfmetrics.registerFont(TTFont(env_name, env_path))
                        return env_name
                except Exception:
                    pass

            # 2) System fonts (Debian): Prefer Abyssinica SIL (Ethiopic) then DejaVu Sans (Latin)
            candidates = [
                ("AbyssinicaSIL", "/usr/share/fonts/truetype/abyssinica/AbyssinicaSIL-Regular.ttf"),
                ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                # Optional fallbacks (if present)
                ("NotoSansEthiopic", "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf"),
                ("NotoSans", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
            ]
            for name, path in candidates:
                try:
                    if os.path.exists(path):
                        pdfmetrics.registerFont(TTFont(name, path))
                        return name
                except Exception:
                    continue
            # Fallback to built-in Helvetica if no Unicode font found
            return "Helvetica"

        def build_pdf_from_structured(data) -> bytes:
            # Simple text-embedded PDF using ReportLab
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=A4)
            width, height = A4
            left = 15 * mm
            top = height - 20 * mm
            line_h = 6 * mm
            y = top
            font_name = _register_unicode_font()
            c.setFont(font_name, 10)
            tables = (data or {}).get('tables', [])
            if not tables:
                c.drawString(left, y, "No structured tables available.")
            else:
                for ti, t in enumerate(tables, start=1):
                    name = t.get('name') or f'Table {ti}'
                    headers = t.get('headers', [])
                    rows = t.get('rows', [])
                    # Bold variant might not exist; keep using the same font
                    c.setFont(font_name, 11)
                    c.drawString(left, y, str(name)[:100])
                    y -= line_h
                    c.setFont(font_name, 10)
                    if headers:
                        c.drawString(left, y, " | ".join([str(h) for h in headers])[:180])
                        y -= line_h
                    for r in rows:
                        line = " | ".join([str(x) if x is not None else "" for x in r])
                        # simple wrapping: split every ~120 chars
                        while line:
                            c.drawString(left, y, line[:120])
                            line = line[120:]
                            y -= line_h
                            if y < 20 * mm:
                                c.showPage(); y = top; c.setFont(font_name, 10)
                    y -= line_h
                    if y < 20 * mm:
                        c.showPage(); y = top; c.setFont(font_name, 10)
            c.showPage()
            c.save()
            return buf.getvalue()

        def respond_pdf(pdf_bytes: bytes, suffix: str = 'extracted'):
            resp = HttpResponse(pdf_bytes, content_type='application/pdf')
            resp['Content-Disposition'] = f'attachment; filename="{base}_{suffix}.pdf"'
            return resp

        if output_format == 'excel':
            # Try Excel export first
            xlsx = None
            try:
                if not structured or not structured.get('tables'):
                    raise ValueError('No tabular data extracted')
                has_content = any(t.get('headers') or t.get('rows') for t in structured.get('tables', []))
                if not has_content:
                    raise ValueError('Empty tables')
                xlsx = pipeline.to_excel(structured)
            except Exception:
                xlsx = None
            if xlsx:
                response = HttpResponse(
                    xlsx,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = f'attachment; filename="{base}_cleaned.xlsx"'
                return response
            else:
                # Embed whatever structure we have into a simple PDF; else fall back to original
                try:
                    pdf_bytes = build_pdf_from_structured(structured)
                except Exception:
                    pdf_bytes = None
                if not pdf_bytes:
                    if ext == '.pdf':
                        pdf_bytes = file_bytes
                    else:
                        pdf_bytes = pipeline.images_to_pdf(original_images)
                return respond_pdf(pdf_bytes)
        else:  # output_format == 'pdf'
            # Prefer building a structured PDF; if no tables, return original/converted PDF
            try:
                if structured and structured.get('tables'):
                    pdf_bytes = build_pdf_from_structured(structured)
                else:
                    pdf_bytes = None
            except Exception:
                pdf_bytes = None
            if not pdf_bytes:
                if ext == '.pdf':
                    pdf_bytes = file_bytes
                else:
                    pdf_bytes = pipeline.images_to_pdf(original_images)
            return respond_pdf(pdf_bytes, suffix='output')
    except Exception as e:
        return HttpResponseBadRequest(f'Processing failed: {e}')
