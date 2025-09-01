from django.core.management.base import BaseCommand
from django.utils import timezone
from parser.services import FileCleanupService, SupabaseStorageService
from parser.models import UserSession, ProcessedDocument
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test file cleanup functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-test-data',
            action='store_true',
            help='Create test data for cleanup testing'
        )

    def handle(self, *args, **options):
        if options['create_test_data']:
            self.create_test_data()
        else:
            self.test_cleanup_functionality()

    def create_test_data(self):
        """Create test data for cleanup testing"""
        self.stdout.write("Creating test data...")
        
        # Create a test session
        test_session = UserSession.objects.create(
            session_key='test_cleanup_session_123',
            is_active=True
        )
        
        # Create test documents
        ProcessedDocument.objects.create(
            session=test_session,
            filename='test_document_1.pdf',
            file_type='pdf',
            file_size=1024,
            processing_status='completed',
            extracted_data={'test': 'data'}
        )
        
        ProcessedDocument.objects.create(
            session=test_session,
            filename='test_document_2.jpg',
            file_type='jpg',
            file_size=2048,
            processing_status='completed',
            extracted_data={'test': 'data2'}
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Created test session {test_session.session_key} with 2 documents"
            )
        )

    def test_cleanup_functionality(self):
        """Test various cleanup functions"""
        self.stdout.write("Testing cleanup functionality...")
        
        cleanup_service = FileCleanupService()
        storage_service = SupabaseStorageService()
        
        # Test 1: Get cleanup candidates
        self.stdout.write("\n1. Testing get_cleanup_candidates...")
        candidates = cleanup_service.get_cleanup_candidates(hours_old=0)  # Get all
        
        if candidates.get('success'):
            self.stdout.write(f"   Found {candidates.get('old_sessions_count', 0)} old sessions")
            self.stdout.write(f"   Found {candidates.get('old_documents_count', 0)} old documents")
            
            storage_stats = candidates.get('storage_stats', {})
            if storage_stats.get('success'):
                self.stdout.write(f"   Storage: {storage_stats.get('total_files', 0)} files, "
                                f"{storage_stats.get('total_size_mb', 0)} MB")
        else:
            self.stdout.write(self.style.ERROR(f"   Error: {candidates.get('error')}"))
        
        # Test 2: Get storage statistics
        self.stdout.write("\n2. Testing storage statistics...")
        stats = storage_service.get_storage_stats()
        
        if stats.get('success'):
            self.stdout.write(f"   Total files: {stats.get('total_files', 0)}")
            self.stdout.write(f"   Total size: {stats.get('total_size_mb', 0)} MB")
            self.stdout.write(f"   Old files: {stats.get('old_files_count', 0)}")
            
            file_types = stats.get('file_types', {})
            if file_types:
                self.stdout.write("   File types:")
                for ext, count in file_types.items():
                    self.stdout.write(f"     {ext or 'no extension'}: {count}")
        else:
            self.stdout.write(self.style.ERROR(f"   Error: {stats.get('error')}"))
        
        # Test 3: Test session cleanup (if test session exists)
        test_session_key = 'test_cleanup_session_123'
        try:
            test_session = UserSession.objects.get(session_key=test_session_key)
            self.stdout.write(f"\n3. Testing manual session cleanup for {test_session_key}...")
            
            # Show what we have before cleanup
            docs_count = test_session.documents.count()
            self.stdout.write(f"   Session has {docs_count} documents before cleanup")
            
            # Perform cleanup
            result = cleanup_service.cleanup_session_manually(test_session_key)
            
            if result.get('success'):
                storage_cleanup = result.get('storage_cleanup', {})
                database_cleanup = result.get('database_cleanup', {})
                
                files_deleted = storage_cleanup.get('files_deleted', 0)
                docs_deleted = database_cleanup.get('documents_deleted', 0)
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"   Cleanup successful: {files_deleted} files, {docs_deleted} documents deleted"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"   Cleanup failed: {result.get('error')}")
                )
                
        except UserSession.DoesNotExist:
            self.stdout.write(f"\n3. No test session found. Run with --create-test-data first.")
        
        # Test 4: Test automatic cleanup
        self.stdout.write("\n4. Testing automatic cleanup (dry run simulation)...")
        result = cleanup_service.cleanup_expired_files(hours_old=24)  # Very old files only
        
        if result.get('success'):
            storage_cleanup = result.get('storage_cleanup', {})
            database_cleanup = result.get('database_cleanup', {})
            
            files_deleted = storage_cleanup.get('files_deleted', 0)
            sessions_deleted = database_cleanup.get('sessions_deleted', 0)
            docs_deleted = database_cleanup.get('documents_deleted', 0)
            
            self.stdout.write(
                f"   Would clean up: {files_deleted} files, {sessions_deleted} sessions, "
                f"{docs_deleted} documents"
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"   Error: {result.get('error')}")
            )
        
        self.stdout.write(self.style.SUCCESS("\nCleanup functionality testing completed!"))