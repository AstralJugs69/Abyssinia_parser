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
from django.conf import settings

# Added: dependencies used in processing and PDF generation
from reportlab.pdfbase import pdfmetrics  # type: ignore
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore
from reportlab.lib.units import mm  # type: ignore
from PIL import Image  # type: ignore

# Added: local OCR/LLM pipeline utilities referenced below
from . import ocr_pipeline as pipeline

from .forms import DocumentUploadForm
# Removed legacy imports of services/models to avoid heavy optional deps
# Required services and models
from .services import SessionService, SupabaseStorageService
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
                        processing_status='pending',
                        source_file_path=upload_result.get('file_path')
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
                    processing_status='pending',
                    source_file_path=upload_result.get('file_path')
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
                    'text': document.extracted_data.get('raw_text', ''),
                    'confidence': document.extracted_data.get('confidence', 0),
                    'word_count': document.extracted_data.get('word_count', 0),
                    'document_id': document.id
                }
            })
        
        # Update status to processing and initialize stage
        document.processing_status = 'processing'
        document.error_message = None  # Clear any previous errors
        document.error_details = {'stage': 'retrieving_file', 'progress': 10}
        document.save()
        
        # Get file from storage (use stored source_file_path if available)
        storage_service = SupabaseStorageService()
        file_path = document.source_file_path or f"{user_session.session_key}/{document.filename}"
        
        try:
            file_content = storage_service.get_file_content(file_path)
        except Exception as storage_error:
            document.processing_status = 'failed'
            document.error_message = f'Storage error: {str(storage_error)}'
            document.error_details = {'stage': 'retrieving_file', 'progress': 10}
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'File retrieval failed',
                'retry_allowed': True
            })
        
        if not file_content:
            document.processing_status = 'failed'
            document.error_message = 'File content is empty or could not be retrieved'
            document.error_details = {'stage': 'retrieving_file', 'progress': 10}
            document.save()
            
            return JsonResponse({
                'success': False,
                'error': 'Empty file',
                'retry_allowed': True
            })
        
        # Determine file extension to branch logic
        ext = os.path.splitext(document.filename)[1].lower()

        # Run simplified pipeline: Vision-only on images
        try:
            document.error_details = {'stage': 'gemini_vision_processing', 'progress': 40}
            document.save(update_fields=['error_details'])

            # Prepare images for Vision depending on file type
            images = []
            if ext == '.pdf':
                # Extract pages as images then preprocess
                pdf_images = pipeline.images_from_pdf(io.BytesIO(file_content))
                for im in pdf_images:
                    buf = io.BytesIO()
                    im.save(buf, format='PNG')
                    images.append(pipeline.preprocess_image(buf.getvalue()))
            else:
                # Single image upload
                images = [pipeline.preprocess_image(file_content)]

            structured_data = pipeline.structure_with_gemini_vision(images)
            extracted_text = 'Processed with Gemini Vision'
        except Exception as processing_error:
            document.processing_status = 'failed'
            document.error_message = f'Processing error: {str(processing_error)}'
            # Choose appropriate stage context for error
            current_stage = 'gemini_vision_processing'
            document.error_details = {'stage': current_stage, 'progress': 45}
            document.save()

            return JsonResponse({
                'success': False,
                'error': 'Document processing failed',
                'retry_allowed': True
            })

        # Step: File generation (Excel + PDF)
        document.error_details = {'stage': 'file_generation', 'progress': 85}
        document.save(update_fields=['error_details'])

        # Excel bytes if we have any structured tables
        excel_bytes = None
        try:
            if structured_data and structured_data.get('tables'):
                has_content = any(t.get('headers') or t.get('rows') for t in structured_data.get('tables', []))
                if has_content:
                    excel_bytes = pipeline.to_excel(structured_data)
        except Exception:
            excel_bytes = None

        # PDF bytes: use structured rendering if possible else fallback to original/converted PDF
        def _register_unicode_font() -> str:
            env_path = os.getenv("PDF_FONT_PATH")
            env_name = os.getenv("PDF_FONT_NAME", "CustomPDFUnicode")
            if env_path:
                try:
                    if os.path.exists(env_path):
                        pdfmetrics.registerFont(TTFont(env_name, env_path))
                        return env_name
                except Exception:
                    pass
            candidates = [
                ("AbyssinicaSIL", "/usr/share/fonts/truetype/abyssinica/AbyssinicaSIL-Regular.ttf"),
                ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
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
            return "Helvetica"

        def _build_pdf_from_structured(data) -> bytes:
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
            # Detect if non-ASCII content present
            def _has_non_ascii(tbls):
                for t in tbls or []:
                    if any(any(ord(ch) > 127 for ch in (h or "")) for h in t.get('headers', []) or []):
                        return True
                    for row in t.get('rows', []) or []:
                        for cell in row:
                            s = str(cell) if cell is not None else ""
                            if any(ord(ch) > 127 for ch in s):
                                return True
                return False

            # If we don't have a Unicode font and content has non-ASCII, signal fallback
            if font_name == "Helvetica" and _has_non_ascii(tables):
                return b""
            if not tables:
                c.drawString(left, y, "No structured tables available.")
            else:
                for ti, t in enumerate(tables, start=1):
                    name = t.get('name') or f'Table {ti}'
                    headers = t.get('headers', [])
                    rows = t.get('rows', [])
                    c.setFont(font_name, 11)
                    c.drawString(left, y, str(name)[:100])
                    y -= line_h
                    c.setFont(font_name, 10)
                    if headers:
                        c.drawString(left, y, " | ".join([str(h) for h in headers])[:180])
                        y -= line_h
                    for r in rows:
                        line = " | ".join([str(x) if x is not None else "" for x in r])
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

        pdf_bytes = None
        try:
            if structured_data and structured_data.get('tables'):
                pdf_bytes = _build_pdf_from_structured(structured_data)
        except Exception:
            pdf_bytes = None
        if not pdf_bytes:
            if ext == '.pdf':
                pdf_bytes = file_content
            else:
                try:
                    # Convert original image(s) to PDF for fallback
                    if ext in ['.jpg', '.jpeg', '.png']:
                        # Recreate original image for PDF
                        orig_img = Image.open(io.BytesIO(file_content))
                        pdf_bytes = pipeline.images_to_pdf([orig_img])
                    else:
                        pdf_bytes = file_content
                except Exception:
                    pdf_bytes = file_content

        # Step: Upload outputs to Supabase
        storage_service = SupabaseStorageService()
        uploaded_files = {}
        document.error_details = {'stage': 'uploading_outputs', 'progress': 90}
        document.save(update_fields=['error_details'])

        from django.core.files.uploadedfile import SimpleUploadedFile
        base_name = os.path.splitext(document.filename)[0]

        if excel_bytes:
            excel_upload = SimpleUploadedFile(
                name=f"{base_name}_cleaned.xlsx",
                content=excel_bytes,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            try:
                up_res = storage_service.upload_file(excel_upload, user_session.session_key)
                if up_res.get('success'):
                    uploaded_files['excel'] = up_res.get('file_path')
            except Exception as e:
                logger.warning(f"Excel upload failed: {e}")

        if pdf_bytes:
            pdf_upload = SimpleUploadedFile(
                name=f"{base_name}_output.pdf",
                content=pdf_bytes,
                content_type='application/pdf'
            )
            try:
                up_res = storage_service.upload_file(pdf_upload, user_session.session_key)
                if up_res.get('success'):
                    uploaded_files['pdf'] = up_res.get('file_path')
            except Exception as e:
                logger.warning(f"PDF upload failed: {e}")
        
        # Step 6: Update document with complete results
        word_count = len((extracted_text or '').split())

        document.extracted_data = {
            'raw_text': extracted_text,
            'parsed_data': structured_data,  # Keep a single structured payload
            'structured_data': structured_data,
            'confidence': 0.8,
            'word_count': word_count,
            'processing_method': 'Vision AI',
            'processed_at': datetime.now().isoformat()
        }

        # Store file paths (now in Supabase storage)
        document.excel_file_path = uploaded_files.get('excel')
        document.pdf_file_path = uploaded_files.get('pdf')
        document.doc_file_path = None
        
        document.processing_status = 'completed'
        document.error_message = None
        document.error_details = {'stage': 'completed', 'progress': 100}
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
        # Include stage/progress if available
        details = document.error_details or {}
        if details:
            response_data['stage'] = details.get('stage')
            response_data['progress'] = details.get('progress')
        
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

# --- Diagnostics and health endpoints ---

@require_http_methods(["GET"])
def health_check(request):
    """Basic health and configuration check for fast diagnostics."""
    try:
        from .services import LLMService, SupabaseStorageService

        # Gemini status
        llm = LLMService()
        gemini = llm.test_api_connection()

        # Supabase status
        storage = SupabaseStorageService()
        supabase_ok = bool(getattr(storage, 'supabase', None))
        bucket = getattr(settings, 'SUPABASE_BUCKET_NAME', None)
        # Light probe to bucket (best-effort)
        storage_probe = None
        if supabase_ok and bucket:
            try:
                storage_probe = storage.supabase.storage.from_(bucket).list("")
                storage_probe = True if storage_probe is not None else False
            except Exception:
                storage_probe = False

        return JsonResponse({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'env': {
                'DEBUG': settings.DEBUG,
                'GEMINI_API_CONFIGURED': bool(getattr(settings, 'GEMINI_API_KEY', None)),
                'SUPABASE_URL_SET': bool(getattr(settings, 'SUPABASE_URL', None)),
                'SUPABASE_KEY_SET': bool(getattr(settings, 'SUPABASE_KEY', None) or getattr(settings, 'SUPABASE_SERVICE_KEY', None)),
                'SUPABASE_BUCKET': bucket or None,
            },
            'services': {
                'gemini': gemini.get('gemini', {}),
                'supabase_client_initialized': supabase_ok,
                'supabase_bucket_access': storage_probe,
            }
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JsonResponse({'success': False, 'error': 'Health check failed'})


    


@require_http_methods(["GET"])
def test_llm_only(request):
    """Run a quick LLM parse on provided text (?text=) or a built-in sample."""
    try:
        sample_text = request.GET.get('text') or (
            "Account Statement for John Doe, Account: 123456789. "
            "Balance: 1000.00. Transactions: 2024-08-01 Deposit 500.00 credit; "
            "2024-08-03 ATM Withdrawal 200.00 debit. Bank: Sample Bank."
        )

        from .services import LLMService
        llm = LLMService()
        result = llm.parse_banking_document(sample_text)
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"LLM test failed: {e}")
        return JsonResponse({'success': False, 'error': 'LLM test failed'})
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
        # Vision-only processing
        use_vision = True

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
            # Preprocess and send to Vision
            img = pipeline.preprocess_image(file_bytes)
            structured = pipeline.structure_with_gemini_vision([img])
        elif ext == '.pdf':
            # Extract images from PDF, preprocess, and send to Vision
            images = pipeline.images_from_pdf(io.BytesIO(file_bytes))
            proc_images = []
            for im in images:
                buf = io.BytesIO()
                im.save(buf, format='PNG')
                proc_images.append(pipeline.preprocess_image(buf.getvalue()))
            structured = pipeline.structure_with_gemini_vision(proc_images)
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
