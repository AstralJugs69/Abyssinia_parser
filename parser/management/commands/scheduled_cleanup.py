from django.core.management.base import BaseCommand
from django.utils import timezone
from parser.services import FileCleanupService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Perform scheduled automatic cleanup of old files and sessions (designed for cron jobs)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=1,
            help='Number of hours after which files should be cleaned up (default: 1)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

    def handle(self, *args, **options):
        if options['verbose']:
            self.stdout.write(f"Starting scheduled cleanup at {timezone.now()}")
        
        cleanup_service = FileCleanupService()
        result = cleanup_service.schedule_automatic_cleanup()
        
        if result.get('success'):
            storage_cleanup = result.get('storage_cleanup', {})
            database_cleanup = result.get('database_cleanup', {})
            
            files_deleted = storage_cleanup.get('files_deleted', 0)
            sessions_deleted = database_cleanup.get('sessions_deleted', 0)
            docs_deleted = database_cleanup.get('documents_deleted', 0)
            
            if options['verbose'] or files_deleted > 0 or sessions_deleted > 0:
                self.stdout.write(
                    f"Cleanup completed: {files_deleted} files, {sessions_deleted} sessions, "
                    f"{docs_deleted} documents deleted"
                )
            
            # Log any errors but don't fail the command
            errors = storage_cleanup.get('errors', [])
            if errors:
                for error in errors:
                    logger.warning(f"Cleanup warning: {error}")
                    if options['verbose']:
                        self.stdout.write(self.style.WARNING(f"Warning: {error}"))
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Scheduled cleanup failed: {error_msg}")
            self.stdout.write(self.style.ERROR(f"Cleanup failed: {error_msg}"))
            # Exit with error code for cron monitoring
            exit(1)
        
        if options['verbose']:
            self.stdout.write(f"Scheduled cleanup completed at {timezone.now()}")