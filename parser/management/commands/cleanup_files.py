from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Disabled: legacy cleanup removed in minimal build.'

    def add_arguments(self, parser):
        parser.add_argument('--noop', action='store_true', help='No operation')

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('cleanup_files command is disabled in the simplified app.'))