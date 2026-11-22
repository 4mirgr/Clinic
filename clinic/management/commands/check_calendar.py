import json

from django.core.management.base import BaseCommand

from clinic.calendar_health import diagnose_calendar


class Command(BaseCommand):
    help = 'Check local Calendar readiness; --probe explicitly permits a read-only FreeBusy request. No events or local models are changed.'

    def add_arguments(self, parser):
        parser.add_argument('--probe', action='store_true', help='Make one short future FreeBusy request if local prerequisites are ready.')
        parser.add_argument('--json', action='store_true', dest='as_json', help='Print safe status identifiers as JSON, never settings values.')

    def handle(self, *args, **options):
        result = diagnose_calendar(probe=options['probe'])
        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False))
            return
        self.stdout.write('Calendar status: ' + result['status'])
        for item in result['issues']:
            self.stdout.write(item['code'] + ': ' + item['message'])
        for label in ('missing_settings', 'invalid_settings'):
            if result[label]:
                self.stdout.write(label + ': ' + ', '.join(result[label]))
        if result['probe_verified'] or not result['issues']:
            self.stdout.write(result['summary'])
        self.stdout.write('No events or local models were changed. ' +
                          ('Read-only probe attempted.' if result['probe_attempted'] else 'No provider request was made.'))
