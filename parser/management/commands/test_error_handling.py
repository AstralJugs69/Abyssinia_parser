from django.core.management.base import BaseCommand
from django.test import RequestFactory
from parser.services import SupabaseStorageService, OCRService, LLMService, ErrorHandler
import io
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test error handling functionality'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--service',
            type=str,
            choices=['storage', 'ocr', 'llm', 'all'],
            default='all',
            help='Which service to test'
        )
    
    def handle(self, *args, **options):
        service = options['service']
        
        self.stdout.write(self.style.SUCCESS('Testing error handling...'))
        
        if service in ['storage', 'all']:
            self.test_storage_errors()
        
        if service in ['ocr', 'all']:
            self.test_ocr_errors()
        
        if service in ['llm', 'all']:
            self.test_llm_errors()
        
        if service in ['all']:
            self.test_error_handler()
        
        self.stdout.write(self.style.SUCCESS('Error handling tests completed'))
    
    def test_storage_errors(self):
        self.stdout.write('Testing storage service errors...')
        
        storage_service = SupabaseStorageService()
        
        # Test with None file
        result = storage_service.upload_file(None, 'test-session')
        self.print_error_result('Storage - None file', result)
        
        # Test with empty file-like object
        empty_file = io.BytesIO(b'')
        empty_file.name = 'empty.txt'
        empty_file.content_type = 'text/plain'
        empty_file.size = 0
        
        result = storage_service.upload_file(empty_file, 'test-session')
        self.print_error_result('Storage - Empty file', result)
    
    def test_ocr_errors(self):
        self.stdout.write('Testing OCR service errors...')
        
        ocr_service = OCRService()
        
        # Test with invalid image data
        invalid_image = io.BytesIO(b'not an image')
        result = ocr_service.extract_text_from_image(invalid_image)
        self.print_error_result('OCR - Invalid image', result)
        
        # Test with empty file
        empty_file = io.BytesIO(b'')
        result = ocr_service.process_file(empty_file, 'jpg')
        self.print_error_result('OCR - Empty file', result)
        
        # Test with unsupported file type
        text_file = io.BytesIO(b'some text')
        result = ocr_service.process_file(text_file, 'xyz')
        self.print_error_result('OCR - Unsupported type', result)
    
    def test_llm_errors(self):
        self.stdout.write('Testing LLM service errors...')
        
        llm_service = LLMService()
        
        # Test with empty text
        result = llm_service.parse_banking_document('', 'banking_document')
        self.print_error_result('LLM - Empty text', result)
        
        # Test with None text
        result = llm_service.parse_banking_document(None, 'banking_document')
        self.print_error_result('LLM - None text', result)
    
    def test_error_handler(self):
        self.stdout.write('Testing ErrorHandler utility...')
        
        # Test various exception types
        exceptions = [
            ConnectionError('Network connection failed'),
            PermissionError('Access denied to file'),
            FileNotFoundError('File not found'),
            MemoryError('Out of memory'),
            ValueError('Invalid value provided')
        ]
        
        for exc in exceptions:
            result = ErrorHandler.get_user_friendly_error(exc)
            self.print_error_result(f'ErrorHandler - {type(exc).__name__}', result)
    
    def print_error_result(self, test_name, result):
        self.stdout.write(f'\n--- {test_name} ---')
        self.stdout.write(f"Success: {result.get('success', 'N/A')}")
        self.stdout.write(f"Error: {result.get('error', 'N/A')}")
        
        if 'details' in result:
            self.stdout.write(f"Details: {result['details']}")
        
        if 'suggestions' in result:
            self.stdout.write(f"Suggestions: {', '.join(result['suggestions'])}")
        
        if 'retry_allowed' in result:
            self.stdout.write(f"Retry allowed: {result['retry_allowed']}")
        
        self.stdout.write('')