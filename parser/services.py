import os
import uuid
from datetime import datetime, timedelta
from django.conf import settings
from supabase import create_client, Client
import logging
import pytesseract
from PIL import Image
import io
import fitz  # PyMuPDF for PDF processing
import json
import re
import time
from typing import Dict, Any, Optional, List
import google.generativeai as genai

# File generation imports
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from docx import Document

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Simplified error handling utility"""
    
    @staticmethod
    def success(message, data=None):
        """Format a success response"""
        response = {'success': True, 'message': message}
        if data is not None:
            response['data'] = data
        return response
    
    @staticmethod
    def error(message, retry_allowed=True):
        """Format an error response"""
        return {
            'success': False,
            'error': message,
            'retry_allowed': retry_allowed
        }
    
    @staticmethod
    def get_user_friendly_error(exception):
        """Convert technical exceptions to user-friendly error messages"""
        return {
            'success': False,
            'error': 'Processing failed',
            'retry_allowed': True
        }


class SupabaseStorageService:
    """Service for handling file uploads to Supabase Storage"""
    
    def __init__(self):
        try:
            # Use service role key for server-side operations
            api_key = getattr(settings, 'SUPABASE_SERVICE_KEY', None) or settings.SUPABASE_KEY
            self.supabase: Client = create_client(
                settings.SUPABASE_URL,
                api_key
            )
            self.bucket_name = settings.SUPABASE_BUCKET_NAME
        except Exception:
            self.supabase = None
    
    def upload_file(self, file, session_key):
        """Upload file to Supabase Storage"""
        if not self.supabase:
            return ErrorHandler.error('Storage unavailable')
        
        if not file or file.size > 10 * 1024 * 1024:
            return ErrorHandler.error('Invalid file')
        
        # Generate filename and read content
        unique_filename = f"{session_key}/{uuid.uuid4()}{os.path.splitext(file.name)[1] or '.tmp'}"
        
        try:
            file.seek(0)
            file_content = file.read()
            if not file_content:
                return ErrorHandler.error('Empty file')
        except Exception:
            return ErrorHandler.error('File read failed')
        
        # Upload with 2-attempt retry
        for attempt in range(2):
            try:
                response = self.supabase.storage.from_(self.bucket_name).upload(
                    path=unique_filename,
                    file=file_content,
                    file_options={"content-type": file.content_type or 'application/octet-stream'}
                )
                
                # Check if upload was successful (newer Supabase client doesn't use status_code)
                if response and not hasattr(response, 'error'):
                    try:
                        public_url = self.supabase.storage.from_(self.bucket_name).get_public_url(unique_filename)
                    except Exception:
                        public_url = None
                    
                    return {
                        'success': True,
                        'file_path': unique_filename,
                        'public_url': public_url
                    }
                    
            except Exception as e:
                logger.error(f"Upload attempt {attempt + 1} failed: {str(e)}")
                pass
            
            if attempt == 0:
                time.sleep(1)
        
        return ErrorHandler.error('Upload failed')
    
    def delete_file(self, file_path):
        """Delete file from storage"""
        try:
            response = self.supabase.storage.from_(self.bucket_name).remove([file_path])
            # Newer Supabase client - check if response exists and no error
            return response and not hasattr(response, 'error')
        except Exception:
            return False
    
    def cleanup_session_files(self, session_key):
        """Clean up session files"""
        try:
            files = self.supabase.storage.from_(self.bucket_name).list(session_key)
            if files:
                file_paths = [f"{session_key}/{f['name']}" for f in files]
                response = self.supabase.storage.from_(self.bucket_name).remove(file_paths)
                return response and not hasattr(response, 'error')
            return True
        except Exception:
            return False
    
    def get_file_content(self, file_path):
        """Download file content"""
        try:
            return self.supabase.storage.from_(self.bucket_name).download(file_path)
        except Exception:
            return None


class FileCleanupService:
    """Service for managing file cleanup and storage maintenance"""
    
    def __init__(self):
        self.storage_service = SupabaseStorageService()
    
    def cleanup_expired_files(self, hours_old=1):
        """Clean up files older than specified hours"""
        from .models import ProcessedDocument, UserSession
        from django.utils import timezone
        
        try:
            cutoff_time = timezone.now() - timedelta(hours=hours_old)
            
            # Find and delete old sessions and documents
            old_sessions = UserSession.objects.filter(last_activity__lt=cutoff_time)
            sessions_count = old_sessions.count()
            documents_count = ProcessedDocument.objects.filter(session__in=old_sessions).count()
            
            # Delete old documents and sessions
            ProcessedDocument.objects.filter(session__in=old_sessions).delete()
            old_sessions.delete()
            
            return ErrorHandler.success(f"Cleaned up {sessions_count} sessions")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")
            return ErrorHandler.error(f"Cleanup failed: {str(e)}")
    
    def cleanup_session_manually(self, session_key):
        """Manually clean up a specific session"""
        from .models import ProcessedDocument, UserSession
        
        try:
            # Clean up storage files
            self.storage_service.cleanup_session_files(session_key)
            
            # Clean up database records
            try:
                session = UserSession.objects.get(session_key=session_key)
                documents_count = session.documents.count()
                session.documents.all().delete()
                session.delete()
                return ErrorHandler.success(f"Cleaned up session with {documents_count} documents")
            except UserSession.DoesNotExist:
                return ErrorHandler.success("Session not found")
                
        except Exception as e:
            logger.error(f"Manual cleanup failed: {str(e)}")
            return ErrorHandler.error(f"Manual cleanup failed: {str(e)}")
    
    def schedule_automatic_cleanup(self):
        """Perform automatic cleanup for scheduled maintenance"""
        result = self.cleanup_expired_files(hours_old=1)
        
        if not result.get('success'):
            logger.error(f"Automatic cleanup failed: {result.get('error')}")
        
        return result


class SessionService:
    """Service for managing user sessions and concurrent limits"""
    
    @staticmethod
    def get_or_create_session(request):
        """Get or create user session with concurrent limit check"""
        from .models import UserSession
        
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        
        try:
            user_session = UserSession.objects.get(session_key=session_key)
            if not user_session.is_active:
                user_session.is_active = True
                user_session.save()
            return user_session, False, None
            
        except UserSession.DoesNotExist:
            if UserSession.get_active_session_count() >= 4:
                return None, False, "System is at capacity (4 users). Please try again later."
            
            user_session = UserSession.objects.create(
                session_key=session_key,
                is_active=True
            )
            return user_session, True, None
    
    @staticmethod
    def cleanup_inactive_sessions():
        """Clean up sessions inactive for more than 1 hour"""
        from .models import UserSession
        
        cutoff_time = datetime.now() - timedelta(hours=1)
        inactive_sessions = UserSession.objects.filter(
            last_activity__lt=cutoff_time,
            is_active=True
        )
        
        cleanup_service = FileCleanupService()
        for session in inactive_sessions:
            cleanup_service.cleanup_session_manually(session.session_key)
        
        inactive_sessions.update(is_active=False)


class OCRService:
    """Simplified service for extracting text from images using Tesseract OCR"""
    
    def __init__(self):
        # Basic Tesseract configuration for Windows
        if os.name == 'nt' and os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
    def extract_text_from_image(self, image_file):
        """Extract text from image file using OCR"""
        try:
            # Load image
            if hasattr(image_file, 'read'):
                image_file.seek(0)
                image_data = image_file.read()
                image = Image.open(io.BytesIO(image_data))
            else:
                image = Image.open(image_file)
            
            # Extract text directly
            extracted_text = pytesseract.image_to_string(image)
            cleaned_text = self._clean_text(extracted_text)
            
            if not cleaned_text.strip():
                return ErrorHandler.error('No readable text found')
            
            return ErrorHandler.success('Text extracted successfully', {
                'text': cleaned_text,
                'word_count': len(cleaned_text.split())
            })
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {str(e)}")
            return ErrorHandler.error('OCR processing failed')
    
    def extract_text_from_pdf(self, pdf_file):
        """Extract text from PDF file, using OCR for image-based PDFs"""
        try:
            # Load PDF
            if hasattr(pdf_file, 'read'):
                pdf_file.seek(0)
                pdf_data = pdf_file.read()
                pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
            else:
                pdf_document = fitz.open(pdf_file)
            
            all_text = []
            
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                page_text = page.get_text()
                
                if page_text.strip():
                    all_text.append(page_text)
                else:
                    # Image-based PDF - use OCR
                    pix = page.get_pixmap()
                    img_data = pix.tobytes("png")
                    image = Image.open(io.BytesIO(img_data))
                    
                    ocr_result = self.extract_text_from_image(image)
                    if ocr_result['success']:
                        all_text.append(ocr_result['data']['text'])
            
            pdf_document.close()
            combined_text = '\n\n'.join(all_text)
            
            return ErrorHandler.success('PDF processed successfully', {
                'text': combined_text,
                'word_count': len(combined_text.split())
            })
            
        except Exception as e:
            logger.error(f"PDF text extraction failed: {str(e)}")
            return ErrorHandler.error('PDF processing failed')
    
    def _clean_text(self, text):
        """Clean extracted text"""
        if not text:
            return ""
        
        # Basic cleanup - remove extra whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
    
    def process_file(self, file_obj, file_type):
        """Process file based on type and extract text"""
        file_type = file_type.lower()
        
        try:
            if file_type in ['jpg', 'jpeg', 'png']:
                return self.extract_text_from_image(file_obj)
            elif file_type == 'pdf':
                return self.extract_text_from_pdf(file_obj)
            elif file_type == 'txt':
                file_obj.seek(0)
                content = file_obj.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8', errors='ignore')
                
                return ErrorHandler.success('Text file processed successfully', {
                    'text': content,
                    'word_count': len(content.split())
                })
            else:
                return ErrorHandler.error(f'Unsupported file type: {file_type}')
                
        except Exception as e:
            logger.error(f"File processing failed for {file_type}: {str(e)}")
            return ErrorHandler.error('File processing failed')


class LLMService:
    """Service for parsing extracted text using Google Gemini API"""
    
    def __init__(self):
        # Initialize Gemini client
        self.gemini_client = None
        if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.gemini_client = genai.GenerativeModel('gemini-1.5-flash')
    
    def parse_banking_document(self, text: str, document_type: str = "banking_document") -> Dict[str, Any]:
        """Parse banking document text using Gemini to extract structured data"""
        if not text or not text.strip():
            return {'success': False, 'error': 'No text provided for parsing', 'data': {}}
        
        if not self.gemini_client:
            return {'success': False, 'error': 'Gemini API not configured', 'data': {}}
        
        # Simple retry logic - try twice
        for attempt in range(2):
            try:
                prompt = self._build_parsing_prompt(text, document_type)
                
                response = self.gemini_client.generate_content(prompt)
                
                if not response.text:
                    continue
                
                parsed_data = self._parse_llm_response(response.text)
                if parsed_data:
                    return {
                        'success': True,
                        'data': parsed_data,
                        'message': 'Document parsed successfully'
                    }
                    
            except Exception as e:
                logger.error(f"Gemini API error (attempt {attempt + 1}): {str(e)}")
                if attempt == 1:  # Last attempt
                    return {'success': False, 'error': f'AI service error: {str(e)}', 'data': {}}
        
        return {'success': False, 'error': 'Failed to parse document', 'data': {}}
    

    
    def _build_parsing_prompt(self, text: str, document_type: str) -> str:
        """Build simplified prompt for banking document parsing"""
        return f"""Extract banking data from this {document_type} and return JSON:

{{
    "document_type": "type",
    "confidence_score": 0.8,
    "personal_information": {{
        "full_name": "name or null",
        "account_number": "account or null",
        "address": "address or null"
    }},
    "financial_data": {{
        "account_balance": "balance or null",
        "transactions": [
            {{"date": "date", "description": "desc", "amount": "amount", "type": "debit/credit"}}
        ]
    }},
    "dates": {{
        "statement_date": "date or null"
    }},
    "bank_information": {{
        "bank_name": "bank or null"
    }}
}}

Return only valid JSON. Use null for missing data.

Text: {text}"""
    
    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response and extract JSON data"""
        try:
            cleaned_text = response_text.strip()
            json_start = cleaned_text.find('{')
            json_end = cleaned_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = cleaned_text[json_start:json_end]
                return json.loads(json_text)
            
            return None
                
        except json.JSONDecodeError:
            return None
        except Exception:
            return None
    
    def test_api_connection(self) -> Dict[str, Any]:
        """Test Gemini API connection"""
        if not self.gemini_client:
            return {'gemini': {'available': False, 'error': 'API key not configured'}}
        
        try:
            test_response = self.gemini_client.generate_content("Test connection. Respond with 'OK'.")
            if test_response.text and 'OK' in test_response.text:
                return {'gemini': {'available': True, 'error': None}}
            else:
                return {'gemini': {'available': False, 'error': 'Unexpected response'}}
        except Exception as e:
            return {'gemini': {'available': False, 'error': str(e)}}


class DataStructuringService:
    """Service for organizing and formatting extracted banking data"""
    
    def structure_banking_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Structure parsed banking data for display and export"""
        try:
            # Simplified data organization
            structured_data = {
                'metadata': {
                    'document_type': parsed_data.get('document_type', 'Unknown'),
                    'processing_timestamp': datetime.now().isoformat()
                },
                'personal_info': self._format_data(parsed_data.get('personal_information', {})),
                'financial_summary': self._format_data(parsed_data.get('financial_data', {})),
                'transactions': self._format_transactions(parsed_data.get('financial_data', {}).get('transactions', [])),
                'loan_details': self._format_data(parsed_data.get('loan_information', {})),
                'bank_details': self._format_data(parsed_data.get('bank_information', {})),
                'important_dates': self._format_data(parsed_data.get('dates', {}))
            }
            
            return ErrorHandler.success('Data structured successfully', structured_data)
            
        except Exception:
            return ErrorHandler.error('Data structuring failed')
    
    def _format_data(self, data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Format data section as key-value pairs"""
        return [
            {'field': key.replace('_', ' ').title(), 'value': str(value)}
            for key, value in data.items() 
            if value and str(value).strip()
        ]
    
    def _format_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format transaction data"""
        return [
            {
                'id': i + 1,
                'date': t.get('date', ''),
                'description': t.get('description', ''),
                'amount': t.get('amount', ''),
                'type': t.get('type', '')
            }
            for i, t in enumerate(transactions) 
            if isinstance(t, dict)
        ]


class FileGenerationService:
    """Simplified service for generating output files in Excel, PDF, and DOC formats"""
    
    def __init__(self):
        self.temp_dir = os.path.join(settings.BASE_DIR, 'temp_files')
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def generate_all_formats(self, structured_data: Dict[str, Any], session_key: str) -> Dict[str, Any]:
        """Generate all three output formats with simplified error handling"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"banking_document_{session_key}_{timestamp}"
        
        results = {'success': True, 'files': {}, 'errors': []}
        
        # Generate files with basic error handling
        for format_type, generator_method in [
            ('excel', self.generate_excel_file),
            ('pdf', self.generate_pdf_file), 
            ('doc', self.generate_doc_file)
        ]:
            result = generator_method(structured_data, base_filename)
            if result.get('success'):
                results['files'][format_type] = {
                    'path': result['path'],
                    'filename': result['filename'],
                    'size': os.path.getsize(result['path']) if os.path.exists(result['path']) else 0
                }
            else:
                results['errors'].append(f"{format_type.upper()} generation failed")
                results['success'] = False
        
        return results
    
    def generate_excel_file(self, data: Dict[str, Any], base_filename: str) -> Dict[str, Any]:
        """Generate Excel file with basic formatting"""
        try:
            wb = Workbook()
            ws = wb.active
            ws.title = "Banking Data"
            
            row = 1
            ws[f'A{row}'] = "Banking Document Report"
            ws[f'A{row}'].font = Font(bold=True, size=14)
            row += 2
            
            # Add sections
            for section_name, section_data in data.items():
                if not section_data:
                    continue
                    
                ws[f'A{row}'] = section_name.replace('_', ' ').title()
                ws[f'A{row}'].font = Font(bold=True)
                row += 1
                
                if isinstance(section_data, list):
                    # Handle transactions
                    if section_name == 'transactions':
                        headers = ['Date', 'Description', 'Amount', 'Type']
                        for col, header in enumerate(headers, 1):
                            ws.cell(row=row, column=col, value=header).font = Font(bold=True)
                        row += 1
                        
                        for transaction in section_data:
                            if isinstance(transaction, dict):
                                ws.cell(row=row, column=1, value=transaction.get('date', ''))
                                ws.cell(row=row, column=2, value=transaction.get('description', ''))
                                ws.cell(row=row, column=3, value=str(transaction.get('amount', '')))
                                ws.cell(row=row, column=4, value=transaction.get('type', ''))
                                row += 1
                elif isinstance(section_data, dict):
                    # Handle key-value data
                    for key, value in section_data.items():
                        if value:
                            ws[f'A{row}'] = key.replace('_', ' ').title()
                            ws[f'B{row}'] = str(value)
                            row += 1
                row += 1
            
            output_path = os.path.join(self.temp_dir, f"{base_filename}.xlsx")
            wb.save(output_path)
            
            return {
                'success': True,
                'path': output_path,
                'filename': os.path.basename(output_path)
            }
        except Exception as e:
            return ErrorHandler.error(f'Excel generation failed: {str(e)}')
    
    def generate_pdf_file(self, data: Dict[str, Any], base_filename: str) -> Dict[str, Any]:
        """Generate PDF file with basic template"""
        try:
            output_path = os.path.join(self.temp_dir, f"{base_filename}.pdf")
            doc = SimpleDocTemplate(output_path, pagesize=letter)
            
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            story.append(Paragraph("Banking Document Report", styles['Title']))
            story.append(Spacer(1, 20))
            
            # Add sections
            for section_name, section_data in data.items():
                if not section_data:
                    continue
                    
                story.append(Paragraph(section_name.replace('_', ' ').title(), styles['Heading2']))
                
                if isinstance(section_data, list) and section_name == 'transactions':
                    # Simple transaction table
                    table_data = [['Date', 'Description', 'Amount', 'Type']]
                    for transaction in section_data:
                        if isinstance(transaction, dict):
                            table_data.append([
                                transaction.get('date', ''),
                                transaction.get('description', ''),
                                str(transaction.get('amount', '')),
                                transaction.get('type', '')
                            ])
                    
                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    story.append(table)
                elif isinstance(section_data, dict):
                    # Simple key-value pairs
                    for key, value in section_data.items():
                        if value:
                            story.append(Paragraph(f"<b>{key.replace('_', ' ').title()}:</b> {value}", styles['Normal']))
                
                story.append(Spacer(1, 12))
            
            doc.build(story)
            
            return {
                'success': True,
                'path': output_path,
                'filename': os.path.basename(output_path)
            }
        except Exception as e:
            return ErrorHandler.error(f'PDF generation failed: {str(e)}')
    
    def generate_doc_file(self, data: Dict[str, Any], base_filename: str) -> Dict[str, Any]:
        """Generate DOC file with essential functionality"""
        try:
            output_path = os.path.join(self.temp_dir, f"{base_filename}.docx")
            doc = Document()
            
            # Title
            doc.add_heading('Banking Document Report', 0)
            
            # Add sections
            for section_name, section_data in data.items():
                if not section_data:
                    continue
                    
                doc.add_heading(section_name.replace('_', ' ').title(), level=1)
                
                if isinstance(section_data, list) and section_name == 'transactions':
                    # Simple transaction table
                    table = doc.add_table(rows=1, cols=4)
                    header_cells = table.rows[0].cells
                    headers = ['Date', 'Description', 'Amount', 'Type']
                    for i, header in enumerate(headers):
                        header_cells[i].text = header
                    
                    for transaction in section_data:
                        if isinstance(transaction, dict):
                            row_cells = table.add_row().cells
                            row_cells[0].text = transaction.get('date', '')
                            row_cells[1].text = transaction.get('description', '')
                            row_cells[2].text = str(transaction.get('amount', ''))
                            row_cells[3].text = transaction.get('type', '')
                elif isinstance(section_data, dict):
                    # Simple key-value pairs
                    for key, value in section_data.items():
                        if value:
                            doc.add_paragraph(f"{key.replace('_', ' ').title()}: {value}")
            
            doc.save(output_path)
            
            return {
                'success': True,
                'path': output_path,
                'filename': os.path.basename(output_path)
            }
        except Exception as e:
            return ErrorHandler.error(f'DOC generation failed: {str(e)}')
    
    def cleanup_temp_files(self, file_paths: List[str]):
        """Clean up temporary files"""
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

