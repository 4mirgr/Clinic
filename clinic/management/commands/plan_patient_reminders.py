from django.core.management.base import BaseCommand
from django.db import transaction
from clinic.communications import plan_reminders


class Command(BaseCommand):
    help = 'Plan opted-in patient reminders without sending. Dry run unless --commit is specified.'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true', help='Persist the planned outbox rows.')
        parser.add_argument('--dry-run', action='store_true', help='Report prospective count without retaining changes (default).')

    def handle(self, *args, **options):
        with transaction.atomic():
            count = plan_reminders()
            if not options['commit'] or options['dry_run']:
                transaction.set_rollback(True)
        self.stdout.write(f"planned={count} persisted={int(options['commit'] and not options['dry_run'])}; no messages sent")
