"""Delete expired optional website activity; never touch medical records."""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from clinic.models import SiteActivity


class Command(BaseCommand):
    help = 'Purge optional website activity older than the 90-day retention window.'

    def handle(self, *args, **options):
        cutoff = timezone.localdate() - timedelta(days=90)
        total = 0
        while True:
            ids = list(SiteActivity.objects.filter(day__lt=cutoff).values_list('pk', flat=True)[:1000])
            if not ids:
                break
            deleted, _ = SiteActivity.objects.filter(pk__in=ids).delete()
            total += deleted
        self.stdout.write(f'Expired website activity deleted: {total}')
