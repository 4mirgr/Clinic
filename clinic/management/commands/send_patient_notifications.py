import json
from django.core.management.base import BaseCommand
from clinic.communication_models import CHANNELS
from clinic.communications import dispatch, readiness


class Command(BaseCommand):
    help = 'Check/dispatch the consent-aware outbox. Never sends without --send and enabled provider configuration.'

    def add_arguments(self, parser):
        parser.add_argument('--send', action='store_true', help='Actually submit eligible messages to configured providers.')
        parser.add_argument('--dry-run', action='store_true', help='Read-only readiness check; takes precedence over --send.')
        parser.add_argument('--check', action='store_true', help='Print configuration status and read-only due counts, with no network.')
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        dry_run = not options['send'] or options['dry_run'] or options['check']
        status = {key: {'configured': readiness(key)[0], 'reason': readiness(key)[1]} for key, _ in CHANNELS}
        result = dispatch(dry_run=dry_run, limit=options['limit'])
        self.stdout.write(json.dumps({'dry_run': dry_run, 'channels': status, 'outbox': result}, ensure_ascii=False))
