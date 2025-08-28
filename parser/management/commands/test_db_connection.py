from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
from parser.models import UserSession, ProcessedDocument


class Command(BaseCommand):
    help = 'Test database connectivity with Supabase and verify models'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Testing database connection...'))
        
        try:
            # Test basic database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result[0] == 1:
                    self.stdout.write(
                        self.style.SUCCESS('✓ Database connection successful')
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR('✗ Database connection failed')
                    )
                    return
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Database connection failed: {str(e)}')
            )
            return

        try:
            # Test if tables exist by checking model operations
            session_count = UserSession.objects.count()
            document_count = ProcessedDocument.objects.count()
            
            self.stdout.write(
                self.style.SUCCESS(f'✓ UserSession table accessible (count: {session_count})')
            )
            self.stdout.write(
                self.style.SUCCESS(f'✓ ProcessedDocument table accessible (count: {document_count})')
            )
            
            # Test creating a sample session (will be cleaned up)
            test_session = UserSession.objects.create(
                session_key='test_session_12345'
            )
            self.stdout.write(
                self.style.SUCCESS('✓ UserSession model create operation successful')
            )
            
            # Test the custom method
            active_count = UserSession.get_active_session_count()
            self.stdout.write(
                self.style.SUCCESS(f'✓ Active sessions count method works: {active_count}')
            )
            
            # Clean up test data
            test_session.delete()
            self.stdout.write(
                self.style.SUCCESS('✓ Test data cleaned up')
            )
            
            self.stdout.write(
                self.style.SUCCESS('\n🎉 All database tests passed! Models are working correctly.')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Model operation failed: {str(e)}')
            )
            self.stdout.write(
                self.style.WARNING('Make sure to run migrations first: python manage.py migrate')
            )