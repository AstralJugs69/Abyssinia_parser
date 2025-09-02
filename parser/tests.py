from django.test import TestCase
from django.core.exceptions import ValidationError
from parser.models import UserSession, ProcessedDocument


class UserSessionModelTest(TestCase):
    """Test cases for UserSession model"""
    
    def test_create_user_session(self):
        """Test creating a user session"""
        session = UserSession.objects.create(
            session_key='test_session_123'
        )
        self.assertEqual(session.session_key, 'test_session_123')
        self.assertTrue(session.is_active)
        self.assertIsNotNone(session.created_at)
        self.assertIsNotNone(session.last_activity)
    
    def test_session_string_representation(self):
        """Test string representation of session"""
        session = UserSession.objects.create(
            session_key='test_session_456'
        )
        expected = "Session test_ses... - Active"
        self.assertEqual(str(session), expected)
    
    def test_deactivate_session(self):
        """Test deactivating a session"""
        session = UserSession.objects.create(
            session_key='test_session_789'
        )
        self.assertTrue(session.is_active)
        
        session.deactivate()
        self.assertFalse(session.is_active)
    
    def test_get_active_session_count(self):
        """Test getting active session count"""
        # Create some sessions
        UserSession.objects.create(session_key='active_1')
        UserSession.objects.create(session_key='active_2')
        inactive_session = UserSession.objects.create(session_key='inactive_1')
        inactive_session.deactivate()
        
        active_count = UserSession.get_active_session_count()
        self.assertEqual(active_count, 2)


class ProcessedDocumentModelTest(TestCase):
    """Test cases for ProcessedDocument model"""
    
    def setUp(self):
        """Set up test data"""
        self.session = UserSession.objects.create(
            session_key='test_doc_session'
        )
    
    def test_create_processed_document(self):
        """Test creating a processed document"""
        doc = ProcessedDocument.objects.create(
            session=self.session,
            filename='test_document.pdf',
            file_type='pdf',
            file_size=1024,
            extracted_data={'test': 'data'}
        )
        
        self.assertEqual(doc.filename, 'test_document.pdf')
        self.assertEqual(doc.file_type, 'pdf')
        self.assertEqual(doc.file_size, 1024)
        self.assertEqual(doc.extracted_data, {'test': 'data'})
        self.assertEqual(doc.processing_status, 'pending')
        self.assertIsNone(doc.error_message)
    
    def test_document_string_representation(self):
        """Test string representation of document"""
        doc = ProcessedDocument.objects.create(
            session=self.session,
            filename='bank_statement.jpg',
            file_type='jpg',
            file_size=2048,
            processing_status='completed'
        )
        expected = "bank_statement.jpg - Completed"
        self.assertEqual(str(doc), expected)
    
    def test_is_processing_complete_property(self):
        """Test is_processing_complete property"""
        doc = ProcessedDocument.objects.create(
            session=self.session,
            filename='test.txt',
            file_type='txt',
            file_size=512
        )
        
        # Initially pending
        self.assertFalse(doc.is_processing_complete)
        
        # Mark as completed
        doc.processing_status = 'completed'
        doc.save()
        self.assertTrue(doc.is_processing_complete)
    
    def test_has_output_files_property(self):
        """Test has_output_files property"""
        doc = ProcessedDocument.objects.create(
            session=self.session,
            filename='test.png',
            file_type='png',
            file_size=1536
        )
        
        # Initially no output files
        self.assertFalse(doc.has_output_files)
        
        # Add all output files
        doc.excel_file_path = '/path/to/output.xlsx'
        doc.pdf_file_path = '/path/to/output.pdf'
        doc.doc_file_path = '/path/to/output.docx'
        doc.save()
        
        self.assertTrue(doc.has_output_files)
    
    def test_file_type_choices(self):
        """Test that file type choices are enforced"""
        doc = ProcessedDocument.objects.create(
            session=self.session,
            filename='test.jpg',
            file_type='jpg',  # Valid choice
            file_size=1024
        )
        self.assertEqual(doc.file_type, 'jpg')
    
    def test_session_relationship(self):
        """Test relationship between session and documents"""
        doc1 = ProcessedDocument.objects.create(
            session=self.session,
            filename='doc1.pdf',
            file_type='pdf',
            file_size=1024
        )
        doc2 = ProcessedDocument.objects.create(
            session=self.session,
            filename='doc2.txt',
            file_type='txt',
            file_size=512
        )
        
        # Test reverse relationship
        session_docs = self.session.documents.all()
        self.assertEqual(session_docs.count(), 2)
        self.assertIn(doc1, session_docs)
        self.assertIn(doc2, session_docs)


from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.contrib.sessions.models import Session
from unittest.mock import patch, MagicMock
import json
import os

from .forms import DocumentUploadForm
from .services import SupabaseStorageService, SessionService


class DocumentUploadFormTest(TestCase):
    """Test cases for DocumentUploadForm validation"""
    
    def setUp(self):
        self.valid_jpg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF'  # Basic JPEG header
        self.valid_png_content = b'\x89PNG\r\n\x1a\n'  # Basic PNG header
        self.valid_pdf_content = b'%PDF-1.4'  # Basic PDF header
        self.valid_txt_content = b'This is a test text file content'
    
    def test_valid_jpg_file(self):
        """Test uploading a valid JPG file"""
        file = SimpleUploadedFile(
            "test.jpg",
            self.valid_jpg_content,
            content_type="image/jpeg"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_file_type(), 'jpg')
    
    def test_valid_jpeg_file(self):
        """Test uploading a valid JPEG file"""
        file = SimpleUploadedFile(
            "test.jpeg",
            self.valid_jpg_content,
            content_type="image/jpeg"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_file_type(), 'jpg')
    
    def test_valid_png_file(self):
        """Test uploading a valid PNG file"""
        file = SimpleUploadedFile(
            "test.png",
            self.valid_png_content,
            content_type="image/png"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_file_type(), 'png')
    
    def test_valid_pdf_file(self):
        """Test uploading a valid PDF file"""
        file = SimpleUploadedFile(
            "test.pdf",
            self.valid_pdf_content,
            content_type="application/pdf"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_file_type(), 'pdf')
    
    def test_valid_txt_file(self):
        """Test uploading a valid TXT file"""
        file = SimpleUploadedFile(
            "test.txt",
            self.valid_txt_content,
            content_type="text/plain"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_file_type(), 'txt')
    
    def test_file_size_limit_exceeded(self):
        """Test file size validation - should reject files over 10MB"""
        large_content = b'x' * (11 * 1024 * 1024)  # 11MB
        file = SimpleUploadedFile(
            "large_file.jpg",
            large_content,
            content_type="image/jpeg"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertFalse(form.is_valid())
        self.assertIn('File size', str(form.errors['file']))
    
    def test_file_size_limit_boundary(self):
        """Test file size validation at boundary - should accept exactly 10MB"""
        boundary_content = b'x' * (10 * 1024 * 1024)  # Exactly 10MB
        file = SimpleUploadedFile(
            "boundary_file.jpg",
            boundary_content,
            content_type="image/jpeg"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertTrue(form.is_valid())
    
    def test_invalid_file_extension(self):
        """Test invalid file extension rejection"""
        file = SimpleUploadedFile(
            "test.doc",
            b"document content",
            content_type="application/msword"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertFalse(form.is_valid())
        self.assertIn('File type', str(form.errors['file']))
    
    def test_no_file_provided(self):
        """Test validation when no file is provided"""
        form = DocumentUploadForm(files={})
        self.assertFalse(form.is_valid())
        self.assertIn('This field is required', str(form.errors['file']))
    
    def test_invalid_image_content_type(self):
        """Test invalid content type for image files"""
        file = SimpleUploadedFile(
            "test.jpg",
            b"not an image",
            content_type="text/plain"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid image file', str(form.errors['file']))
    
    def test_invalid_pdf_content_type(self):
        """Test invalid content type for PDF files"""
        file = SimpleUploadedFile(
            "test.pdf",
            b"not a pdf",
            content_type="text/plain"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid PDF file', str(form.errors['file']))
    
    def test_invalid_txt_content_type(self):
        """Test invalid content type for text files"""
        file = SimpleUploadedFile(
            "test.txt",
            b"text content",
            content_type="application/octet-stream"
        )
        form = DocumentUploadForm(files={'file': file})
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid text file', str(form.errors['file']))


class SessionServiceTest(TestCase):
    """Test cases for SessionService"""
    
    def setUp(self):
        from django.test import Client
        self.client = Client()
    
    def test_create_new_session(self):
        """Test creating a new session when none exists"""
        request = self.client.get('/').wsgi_request
        request.session.create()
        
        session, created, error = SessionService.get_or_create_session(request)
        
        self.assertIsNotNone(session)
        self.assertTrue(created)
        self.assertIsNone(error)
        self.assertTrue(session.is_active)
    
    def test_get_existing_session(self):
        """Test getting an existing active session"""
        request = self.client.get('/').wsgi_request
        request.session.create()
        
        # Create session first time
        session1, created1, error1 = SessionService.get_or_create_session(request)
        
        # Get same session second time
        session2, created2, error2 = SessionService.get_or_create_session(request)
        
        self.assertEqual(session1.id, session2.id)
        self.assertFalse(created2)
        self.assertIsNone(error2)
    
    def test_reactivate_inactive_session(self):
        """Test reactivating an inactive session"""
        request = self.client.get('/').wsgi_request
        request.session.create()
        
        # Create and deactivate session
        session, created, error = SessionService.get_or_create_session(request)
        session.deactivate()
        
        # Try to get session again
        session2, created2, error2 = SessionService.get_or_create_session(request)
        
        self.assertEqual(session.id, session2.id)
        self.assertFalse(created2)
        self.assertIsNone(error2)
        self.assertTrue(session2.is_active)
    
    def test_concurrent_user_limit(self):
        """Test concurrent user limit enforcement"""
        # Create 4 active sessions
        for i in range(4):
            UserSession.objects.create(
                session_key=f'session_{i}',
                is_active=True
            )
        
        # Try to create 5th session
        request = self.client.get('/').wsgi_request
        request.session.create()
        
        session, created, error = SessionService.get_or_create_session(request)
        
        self.assertIsNone(session)
        self.assertFalse(created)
        self.assertIn('System is at capacity', error)


class SupabaseStorageServiceTest(TestCase):
    """Test cases for SupabaseStorageService"""
    
    @patch('parser.services.create_client')
    def setUp(self, mock_create_client):
        self.mock_supabase = MagicMock()
        mock_create_client.return_value = self.mock_supabase
        self.storage_service = SupabaseStorageService()
    
    def test_upload_file_success(self):
        """Test successful file upload"""
        # Mock successful upload response
        mock_response = MagicMock()
        mock_response.status_code = 200
        self.mock_supabase.storage.from_().upload.return_value = mock_response
        self.mock_supabase.storage.from_().get_public_url.return_value = "http://example.com/file.jpg"
        
        file = SimpleUploadedFile(
            "test.jpg",
            b"test content",
            content_type="image/jpeg"
        )
        
        result = self.storage_service.upload_file(file, "test_session")
        
        self.assertTrue(result['success'])
        self.assertIn('file_path', result)
        self.assertIn('public_url', result)
    
    def test_upload_file_failure(self):
        """Test failed file upload"""
        # Mock failed upload response
        mock_response = MagicMock()
        mock_response.status_code = 400
        self.mock_supabase.storage.from_().upload.return_value = mock_response
        
        file = SimpleUploadedFile(
            "test.jpg",
            b"test content",
            content_type="image/jpeg"
        )
        
        result = self.storage_service.upload_file(file, "test_session")
        
        self.assertFalse(result['success'])
        self.assertIn('error', result)
    
    def test_delete_file_success(self):
        """Test successful file deletion"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        self.mock_supabase.storage.from_().remove.return_value = mock_response
        
        result = self.storage_service.delete_file("test/file.jpg")
        
        self.assertTrue(result)
    
    def test_delete_file_failure(self):
        """Test failed file deletion"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        self.mock_supabase.storage.from_().remove.return_value = mock_response
        
        result = self.storage_service.delete_file("test/file.jpg")
        
        self.assertFalse(result)


class DocumentUploadViewTest(TestCase):
    """Test cases for DocumentUploadView"""
    
    def setUp(self):
        from django.test import Client
        self.client = Client()
        self.upload_url = reverse('upload')
        self.ajax_url = reverse('upload_ajax')
    
    def test_get_upload_page(self):
        """Test GET request to upload page"""
        response = self.client.get(self.upload_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload Document')
        self.assertContains(response, 'Drag and drop')
    
    @patch('parser.views.SupabaseStorageService')
    def test_ajax_upload_success(self, mock_storage_service):
        """Test successful AJAX file upload"""
        # Mock successful storage upload
        mock_storage_instance = mock_storage_service.return_value
        mock_storage_instance.upload_file.return_value = {
            'success': True,
            'file_path': 'test/file.jpg',
            'public_url': 'http://example.com/file.jpg'
        }
        
        file = SimpleUploadedFile(
            "test.jpg",
            b"test image content",
            content_type="image/jpeg"
        )
        
        response = self.client.post(
            self.ajax_url,
            {'file': file},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('document_id', data)
        self.assertEqual(data['filename'], 'test.jpg')
    
    def test_ajax_upload_invalid_file(self):
        """Test AJAX upload with invalid file"""
        file = SimpleUploadedFile(
            "test.doc",
            b"document content",
            content_type="application/msword"
        )
        
        response = self.client.post(
            self.ajax_url,
            {'file': file},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_ajax_upload_no_file(self):
        """Test AJAX upload with no file"""
        response = self.client.post(
            self.ajax_url,
            {},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('No file provided', data['error'])
    
    def test_concurrent_user_limit_ajax(self):
        """Test concurrent user limit in AJAX upload"""
        # Create 4 active sessions
        for i in range(4):
            UserSession.objects.create(
                session_key=f'session_{i}',
                is_active=True
            )
        
        file = SimpleUploadedFile(
            "test.jpg",
            b"test content",
            content_type="image/jpeg"
        )
        
        response = self.client.post(
            self.ajax_url,
            {'file': file},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('System is at capacity', data['error'])


class DocumentProcessingIntegrationTest(TestCase):
    """Integration test for complete document processing workflow"""
    
    def setUp(self):
        from django.test import Client
        self.client = Client()
        self.session = UserSession.objects.create(session_key='test_integration_session')
        
        # Create a test document
        self.document = ProcessedDocument.objects.create(
            session=self.session,
            filename='test_bank_statement.txt',
            file_type='txt',
            file_size=1024,
            processing_status='pending'
        )
    
    @patch('parser.views.SessionService')
    @patch('parser.services.LLMService')
    @patch('parser.services.DataStructuringService')
    @patch('parser.services.FileGenerationService')
    @patch('parser.services.SupabaseStorageService')
    def test_complete_processing_workflow(self, mock_storage, mock_file_gen, mock_structuring, mock_llm, mock_session_service):
        """Test the complete end-to-end processing workflow"""
        
        # Mock session service to return our test session
        mock_session_service.get_or_create_session.return_value = (self.session, False, None)
        
        # Mock LLM service
        mock_llm_instance = mock_llm.return_value
        mock_llm_instance.parse_banking_document.return_value = {
            'success': True,
            'data': {
                'account_number': '123456789',
                'balance': '$1,000.00',
                'document_type': 'bank_statement'
            }
        }
        
        # Mock data structuring service
        mock_structuring_instance = mock_structuring.return_value
        mock_structuring_instance.structure_banking_data.return_value = {
            'success': True,
            'data': {
                'personal_info': {'name': 'John Doe'},
                'financial_data': {'account_number': '123456789', 'balance': '$1,000.00'},
                'dates': {'document_date': '2024-01-01'},
                'identifiers': {'reference_numbers': ['REF123']}
            }
        }
        
        # Mock file generation service
        mock_file_gen_instance = mock_file_gen.return_value
        mock_file_gen_instance.generate_all_formats.return_value = {
            'success': True,
            'files': {
                'excel': {'path': '/tmp/test.xlsx', 'filename': 'test.xlsx'},
                'pdf': {'path': '/tmp/test.pdf', 'filename': 'test.pdf'},
                'doc': {'path': '/tmp/test.docx', 'filename': 'test.docx'}
            }
        }
        
        # Mock storage service for file retrieval and upload
        mock_storage_instance = mock_storage.return_value
        mock_storage_instance.get_file_content.return_value = b'test file content'
        mock_storage_instance.upload_file.return_value = {
            'success': True,
            'file_path': 'session/uploaded_file.xlsx'
        }
        
        # Also mock the storage service class itself for the new instance created in the view
        mock_storage.return_value.get_file_content.return_value = b'test file content'
        mock_storage.return_value.upload_file.return_value = {
            'success': True,
            'file_path': 'session/uploaded_file.xlsx'
        }
        
        # Mock file existence and reading
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=b'generated file content')), \
             patch('os.remove'):
            
            # Make the processing request
            response = self.client.post(
                reverse('process_document'),
                json.dumps({'document_id': self.document.id}),
                content_type='application/json',
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        # Debug: print the actual response if test fails
        if not data.get('success'):
            print(f"Test failed with response: {data}")
        
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'Document processed successfully')
        self.assertTrue(data['data']['files_generated'])
        
        # Verify document was updated
        self.document.refresh_from_db()
        self.assertEqual(self.document.processing_status, 'completed')
        self.assertIsNotNone(self.document.extracted_data)
        self.assertIsNotNone(self.document.excel_file_path)
        self.assertIsNotNone(self.document.pdf_file_path)
        self.assertIsNotNone(self.document.doc_file_path)
    
    def test_get_document_results(self):
        """Test getting results for a processed document"""
        # Set up a completed document
        self.document.processing_status = 'completed'
        self.document.extracted_data = {
            'structured_data': {
                'personal_info': {'name': 'John Doe'},
                'financial_data': {'balance': '$1,000.00'}
            },
            'confidence': 0.9,
            'processing_method': 'LLM'
        }
        self.document.save()
        
        # Make request to get results
        response = self.client.get(reverse('document_results', args=[self.document.id]))
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['document_id'], self.document.id)
        self.assertIn('results', data)
        self.assertEqual(data['confidence'], 0.9)
    
    @patch('parser.views.SupabaseStorageService')
    def test_download_file(self, mock_storage):
        """Test downloading generated files"""
        # Set up a completed document with file paths
        self.document.processing_status = 'completed'
        self.document.excel_file_path = 'session/test.xlsx'
        self.document.save()
        
        # Mock storage service
        mock_storage_instance = mock_storage.return_value
        mock_storage_instance.get_file_content.return_value = b'excel file content'
        
        # Make download request
        response = self.client.get(reverse('download_file', args=[self.document.id, 'excel']))
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment', response['Content-Disposition'])


# Import mock_open for file mocking
from unittest.mock import mock_open